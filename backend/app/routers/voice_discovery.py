"""Voice Discovery router — sample analysis, interview, and profile compilation.

This is the core product flow:
  1. POST /analyze — analyze a writing sample for style markers
  2. POST /interview — adaptive conversational interview (SSE)
  3. POST /finalize — compile interview into Voice DNA Profile
"""

import json
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    FinalizeRequest,
    FinalizeResponse,
    InterviewRequest,
    StyleMarkers,
)
from app.models.voice_session import (
    create_session,
    delete_session,
    get_session,
)
from app.prompts.interview_conductor import INTERVIEW_START, INTERVIEW_SYSTEM
from app.prompts.profile_compiler import (
    PROFILE_COMPILER_SYSTEM,
    PROFILE_COMPILER_USER,
)
from app.prompts.sample_analysis import SAMPLE_ANALYSIS_SYSTEM, SAMPLE_ANALYSIS_USER
from app.services import llm_service
from app.services.supabase_client import get_supabase_client
from app.prompts.sample_analysis import SAMPLE_ANALYSIS_SYSTEM, build_sample_analysis_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-discovery", tags=["voice-discovery"])

INTERVIEW_COMPLETE_SIGNAL = "[INTERVIEW_COMPLETE]"
THOUGHT_OPEN_TAG = "<thought_process>"
THOUGHT_CLOSE_TAG = "</thought_process>"


# ---------------------------------------------------------------------------
# 1. Sample Analysis
# ---------------------------------------------------------------------------


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_writing_sample(
    analyze_request: AnalyzeRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> AnalyzeResponse:
    """Analyze a writing sample and return style markers.

    Creates an in-memory session for the subsequent interview steps.
    Retries once if the LLM returns invalid JSON.
    """
    user_prompt = build_sample_analysis_user(
        writing_sample=analyze_request.writing_sample,
        sample_context=analyze_request.sample_context,
    )

    style_markers_dict = await _call_llm_json(
        system_prompt=SAMPLE_ANALYSIS_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.7,
        error_message="Analysis failed — please try again.",
    )

    # Validate the shape matches our schema
    try:
        style_markers = StyleMarkers(**style_markers_dict)
    except Exception:
        logger.error("Style markers failed validation: %s", style_markers_dict)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Analysis failed — please try again.",
        )

    session_id = create_session(
        user_id=user_id,
        writing_sample=analyze_request.writing_sample,
        style_markers=style_markers.model_dump(),
    )

    return AnalyzeResponse(
        session_id=session_id,
        style_markers=style_markers,
    )


# ---------------------------------------------------------------------------
# 2. Conversational Interview (SSE)
# ---------------------------------------------------------------------------


@router.post("/interview")
async def conduct_interview(
    interview_request: InterviewRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> StreamingResponse:
    """Stream the next interview question/response via SSE.

    The AI adapts each question based on the writing sample analysis
    and all prior interview exchanges. Signals completion with
    [INTERVIEW_COMPLETE] which is stripped before sending to the client.
    """
    session = get_session(interview_request.session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Your session expired. Please start a new voice discovery.",
        )

    # Append user message if this isn't the very first call
    if interview_request.user_message:
        session.interview_messages.append(
            {"role": "user", "content": interview_request.user_message}
        )

    # Build system prompt with style markers injected
    system_prompt = INTERVIEW_SYSTEM.format(
        style_markers_json=json.dumps(session.style_markers, indent=2),
    )

    # Build conversation messages for the LLM
    messages: list[dict[str, str]] = []
    if not session.interview_messages:
        # First call — use the interview start prompt
        messages.append({"role": "user", "content": INTERVIEW_START})
    else:
        messages.extend(session.interview_messages)

    question_number = (len(session.interview_messages) // 2) + 1

    async def stream_interview() -> ...:
        """Stream tokens, strip thought blocks, detect completion signal.

        Strategy: buffer the last N chars to detect the completion
        signal and <thought_process> tags without streaming them to
        the client. When inside a thought block, all tokens are
        suppressed until the closing tag is found. All other tokens
        are sent immediately.
        """
        full_response = ""
        interview_complete = False
        inside_thought_block = False
        # Buffer to hold tokens that might be part of a signal or tag
        pending_buffer = ""
        signal_len = len(INTERVIEW_COMPLETE_SIGNAL)
        max_tag_len = max(signal_len, len(THOUGHT_OPEN_TAG), len(THOUGHT_CLOSE_TAG))

        try:
            async for token in llm_service.generate_stream(
                system_prompt=system_prompt,
                messages=messages,
                temperature=0.8,
            ):
                full_response += token
                pending_buffer += token

                # --- Inside a thought block: suppress output, watch for close tag ---
                if inside_thought_block:
                    if THOUGHT_CLOSE_TAG in pending_buffer:
                        inside_thought_block = False
                        # Discard everything up to and including the close tag
                        pending_buffer = pending_buffer.split(THOUGHT_CLOSE_TAG, 1)[1]
                    elif len(pending_buffer) > len(THOUGHT_CLOSE_TAG):
                        # Trim buffer — only need enough to detect partial close tag
                        pending_buffer = pending_buffer[-len(THOUGHT_CLOSE_TAG):]
                    continue

                # --- Not inside a thought block ---

                # Check for thought_process opening tag
                if THOUGHT_OPEN_TAG in pending_buffer:
                    inside_thought_block = True
                    before_tag = pending_buffer.split(THOUGHT_OPEN_TAG, 1)[0]
                    if before_tag:
                        yield f"data: {json.dumps({'type': 'token', 'content': before_tag})}\n\n"
                    # Keep remainder after opening tag for close-tag detection
                    pending_buffer = pending_buffer.split(THOUGHT_OPEN_TAG, 1)[1]
                    continue

                # Check for completion signal
                if INTERVIEW_COMPLETE_SIGNAL in pending_buffer:
                    interview_complete = True
                    # Flush anything before the signal
                    before_signal = pending_buffer.split(INTERVIEW_COMPLETE_SIGNAL)[0]
                    if before_signal:
                        yield f"data: {json.dumps({'type': 'token', 'content': before_signal})}\n\n"
                    pending_buffer = ""
                    continue

                # Flush safe portion that can't be the start of any tag/signal
                if len(pending_buffer) > max_tag_len:
                    safe = pending_buffer[:-max_tag_len]
                    pending_buffer = pending_buffer[-max_tag_len:]
                    yield f"data: {json.dumps({'type': 'token', 'content': safe})}\n\n"

        except Exception as e:
            logger.error("Interview stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Interview interrupted — please try again.'})}\n\n"
            return

        # Flush remaining buffer (excluding signal if present)
        if pending_buffer and not interview_complete and not inside_thought_block:
            yield f"data: {json.dumps({'type': 'token', 'content': pending_buffer})}\n\n"

        # Clean the response for storage — strip signal and thought blocks
        clean_response = full_response.replace(INTERVIEW_COMPLETE_SIGNAL, "")
        clean_response = re.sub(
            r"<thought_process>.*?</thought_process>", "", clean_response, flags=re.DOTALL
        ).strip()

        # Store the assistant response in session
        session.interview_messages.append(
            {"role": "assistant", "content": clean_response}
        )

        if interview_complete:
            session.interview_complete = True

        yield f"data: {json.dumps({'type': 'done', 'interview_complete': interview_complete, 'question_number': question_number})}\n\n"

    return StreamingResponse(
        stream_interview(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 3. Profile Compilation
# ---------------------------------------------------------------------------


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_profile(
    finalize_request: FinalizeRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> FinalizeResponse:
    """Compile the full Voice DNA Profile from the completed interview.

    Stores the profile in Supabase and cleans up the in-memory session.
    """
    session = get_session(finalize_request.session_id, user_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Your session expired. Please start a new voice discovery.",
        )

    # Require at least 7 interview exchanges (user+assistant pairs)
    exchange_count = sum(
        1 for m in session.interview_messages if m["role"] == "assistant"
    )
    if exchange_count < 7 and not session.interview_complete:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please complete the interview before finalizing your profile.",
        )

    # Build interview transcript for the compiler
    transcript_lines = []
    for msg in session.interview_messages:
        role_label = "Interviewer" if msg["role"] == "assistant" else "Writer"
        transcript_lines.append(f"{role_label}: {msg['content']}")
    interview_transcript = "\n\n".join(transcript_lines)

    # Truncate writing sample to first 2000 words
    words = session.writing_sample.split()
    writing_sample_truncated = " ".join(words[:2000])

    user_prompt = PROFILE_COMPILER_USER.format(
        style_markers_json=json.dumps(session.style_markers, indent=2),
        interview_transcript=interview_transcript,
        writing_sample_truncated=writing_sample_truncated,
    )

    profile_dict = await _call_llm_json(
        system_prompt=PROFILE_COMPILER_SYSTEM,
        user_prompt=user_prompt,
        temperature=0.7,
        max_tokens=8000,
        error_message="Profile compilation failed — please try again.",
    )

    # Store in Supabase
    try:
        supabase = get_supabase_client()
        insert_data = {
            "user_id": user_id,
            "profile_name": finalize_request.profile_name,
            "literary_dna": profile_dict.get("literary_dna", {}),
            "influences": profile_dict.get("influences", {}),
            "anti_slop": profile_dict.get("anti_slop", {}),
            "voice_instruction": profile_dict.get("voice_instruction", ""),
            "voice_summary": profile_dict.get("voice_summary", ""),
        }
        result = supabase.table("voice_profiles").insert(insert_data).execute()
        profile_id = result.data[0]["id"]
    except Exception as e:
        logger.error("Failed to store voice profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save profile — please try again.",
        )

    # Clean up session
    delete_session(finalize_request.session_id)

    return FinalizeResponse(
        profile_id=profile_id,
        profile_name=finalize_request.profile_name,
        literary_dna=profile_dict.get("literary_dna", {}),
        influences=profile_dict.get("influences", {}),
        anti_slop=profile_dict.get("anti_slop", {}),
        voice_instruction=profile_dict.get("voice_instruction", ""),
        voice_summary=profile_dict.get("voice_summary", ""),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4000,
    error_message: str = "Request failed — please try again.",
) -> dict:
    """Call the LLM and parse JSON response. Retries once on parse failure."""
    for attempt in range(2):
        try:
            raw = await llm_service.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            # Strip markdown fencing if the LLM wraps it
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                # Remove ```json ... ``` or ``` ... ```
                lines = cleaned.split("\n")
                lines = lines[1:]  # drop opening ```json
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned = "\n".join(lines)

            return json.loads(cleaned)
        except json.JSONDecodeError:
            if attempt == 0:
                logger.warning("LLM returned invalid JSON (attempt %d), retrying", attempt + 1)
                continue
            logger.error("LLM returned invalid JSON after retry: %s", raw[:500])
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_message,
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_message,
            )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=error_message,
    )
