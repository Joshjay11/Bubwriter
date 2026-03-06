"""Conversation import router — upload ChatGPT export for voice enrichment.

Accepts a ChatGPT data export ZIP file, extracts user messages, filters for
personality-rich content, analyzes communication patterns via LLM, and
attaches the results to the active Voice Discovery session.

Privacy: raw conversation content is processed in memory and discarded.
Only the analysis output (structured personality markers) is kept. No raw
messages are logged or persisted.
"""

import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.models.voice_session import get_session
from app.prompts.conversation_analysis import (
    CONVERSATION_ANALYSIS_SYSTEM,
    CONVERSATION_ANALYSIS_USER,
)
from app.services import llm_service
from app.services.conversation_filter import filter_messages
from app.services.conversation_parser import parse_chatgpt_export

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-discovery", tags=["voice-discovery"])

MAX_FILE_SIZE = 200 * 1024 * 1024  # 200 MB
MAX_ANALYSIS_WORDS = 50_000


@router.post("/import-conversations")
async def import_conversations(
    user_id: Annotated[str, Depends(get_current_user)],
    file: UploadFile = File(...),
    session_id: str = Form(...),
) -> StreamingResponse:
    """Upload a ChatGPT export ZIP and analyze conversation patterns.

    Streams SSE progress events as the pipeline runs through 5 stages:
    extract → filter → prepare → analyze → store. The final event
    contains stats about the processed data.

    The raw conversation content is discarded after analysis — only the
    structured personality markers are attached to the session.
    """
    # Validate session exists and belongs to user
    session = get_session(session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Your session expired. Please start a new voice discovery.",
        )

    # Prevent re-uploads
    if session.conversation_analysis is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conversations have already been imported for this session.",
        )

    # Read file into memory (check size)
    file_contents = await file.read()
    if len(file_contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is too large. Maximum size is 200 MB.",
        )

    async def stream_pipeline() -> ...:
        """Run the 5-stage import pipeline, emitting SSE progress events."""
        total_conversations = 0
        filtered_count = 0
        analysis_word_count = 0

        # --- Stage 1: Extract ---
        try:
            yield _sse_progress("extract", "Extracting conversations...", 10)
            all_messages = parse_chatgpt_export(file_contents)
            total_conversations = len(
                {m["conversation_title"] for m in all_messages}
            )
            yield _sse_progress(
                "extract",
                f"Found {total_conversations} conversations, "
                f"{len(all_messages)} user messages",
                20,
            )
        except ValueError as e:
            yield _sse_error(str(e))
            return
        except Exception:
            logger.exception("Unexpected error during conversation extraction")
            yield _sse_error(
                "Failed to read the export file. Please check the format "
                "and try again."
            )
            return

        # --- Stage 2: Filter ---
        try:
            yield _sse_progress("filter", "Filtering for personality-rich messages...", 30)
            filtered = await filter_messages(all_messages)
            filtered_count = len(filtered)
            if filtered_count == 0:
                yield _sse_error(
                    "No personality-rich messages found in the export. "
                    "The conversations may be too short or too technical."
                )
                return
            yield _sse_progress(
                "filter",
                f"Selected {filtered_count} personality-rich messages "
                f"from {len(all_messages)} total",
                40,
            )
        except Exception:
            logger.exception("Unexpected error during message filtering")
            yield _sse_error("Failed to filter messages. Please try again.")
            return

        # --- Stage 3: Prepare ---
        try:
            messages_text = "\n---\n".join(m["content"] for m in filtered)
            words = messages_text.split()
            if len(words) > MAX_ANALYSIS_WORDS:
                messages_text = " ".join(words[:MAX_ANALYSIS_WORDS])
            analysis_word_count = min(len(words), MAX_ANALYSIS_WORDS)
            yield _sse_progress(
                "prepare",
                f"Prepared {analysis_word_count:,} words for analysis",
                50,
            )
        except Exception:
            logger.exception("Unexpected error during message preparation")
            yield _sse_error("Failed to prepare messages. Please try again.")
            return

        # --- Stage 4: Analyze ---
        try:
            yield _sse_progress(
                "analyze", "Analyzing communication patterns...", 60
            )
            user_prompt = CONVERSATION_ANALYSIS_USER.format(
                word_count=analysis_word_count,
                message_count=filtered_count,
                messages_text=messages_text,
            )

            raw_analysis = await llm_service.generate(
                system_prompt=CONVERSATION_ANALYSIS_SYSTEM,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=4000,
            )

            # Parse JSON — strip markdown fencing if present
            analysis_dict = _parse_json_response(raw_analysis)

            yield _sse_progress("analyze", "Analysis complete", 90)
        except Exception:
            logger.exception("Conversation analysis LLM call failed")
            yield _sse_error(
                "Analysis failed — the AI couldn't process your conversations. "
                "Please try again."
            )
            return

        # --- Stage 5: Store in session ---
        try:
            session.conversation_analysis = analysis_dict
            session.conversation_stats = {
                "total_conversations": total_conversations,
                "messages_analyzed": filtered_count,
                "words_analyzed": analysis_word_count,
            }

            stats = session.conversation_stats
            yield _sse_done(stats)
        except Exception:
            logger.exception("Failed to store conversation analysis in session")
            yield _sse_error("Failed to save analysis results. Please try again.")
            return

        logger.info(
            "Conversation import complete: %d conversations, "
            "%d messages analyzed, %d words",
            total_conversations,
            filtered_count,
            analysis_word_count,
        )

    return StreamingResponse(
        stream_pipeline(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# SSE event helpers
# ---------------------------------------------------------------------------


def _sse_progress(stage: str, detail: str, percent: int) -> str:
    """Format an SSE progress event."""
    data = {"type": "progress", "stage": stage, "detail": detail, "percent": percent}
    return f"data: {json.dumps(data)}\n\n"


def _sse_done(stats: dict) -> str:
    """Format the final SSE done event with import statistics."""
    data = {"type": "done", "stats": stats}
    return f"data: {json.dumps(data)}\n\n"


def _sse_error(detail: str) -> str:
    """Format an SSE error event."""
    data = {"type": "error", "detail": detail}
    return f"data: {json.dumps(data)}\n\n"


def _parse_json_response(raw: str) -> dict:
    """Parse LLM response as JSON, stripping markdown fencing if present."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]  # drop opening ```json
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    return json.loads(cleaned)
