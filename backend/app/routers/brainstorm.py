"""Brainstorm router — Socratic story development via SSE streaming.

Endpoints:
  POST /brainstorm/start     — Start a new brainstorming session
  POST /brainstorm/respond   — Continue the conversation (SSE streaming)
  POST /brainstorm/evaluate  — Idea viability gate assessment
"""

import asyncio
import json
import logging
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.models.brainstorm_session import (
    create_brainstorm_session,
    get_brainstorm_session,
)
from app.prompts.brainstorm_conductor import (
    BRAINSTORM_CONDUCTOR_SYSTEM,
    BRAINSTORM_START,
    EVALUATE_SYSTEM,
)
from app.services import llm_service
from app.services.voice_extraction_service import (
    refine_project_voice_from_brainstorm,
)

# Trigger background voice extraction every N assistant turns in /respond.
VOICE_EXTRACTION_INTERVAL = 5

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brainstorm", tags=["brainstorm"])

THOUGHT_OPEN_TAG = "<thought_process>"
THOUGHT_CLOSE_TAG = "</thought_process>"


# --- Request Models ---


class BrainstormStartRequest(BaseModel):
    project_id: str | None = None
    genre: str | None = None
    distribution_format: str | None = None


class BrainstormRespondRequest(BaseModel):
    session_id: str
    message: str


class BrainstormEvaluateRequest(BaseModel):
    session_id: str


# --- Endpoints ---


@router.post("/start")
async def start_brainstorm(
    start_request: BrainstormStartRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Start a new brainstorming session.

    Returns a session_id and streams the opening question.
    """
    session_id = create_brainstorm_session(
        user_id=user_id,
        project_id=start_request.project_id,
        genre=start_request.genre,
        distribution_format=start_request.distribution_format,
    )

    session = get_brainstorm_session(session_id, user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create brainstorm session.",
        )

    # Build system prompt with genre context
    genre_context = ""
    if start_request.genre:
        genre_context = (
            f"The writer is working in the {start_request.genre} genre. "
            f"Tailor your questions to genre-specific concerns and conventions."
        )
    if start_request.distribution_format:
        fmt = start_request.distribution_format.replace("_", " ")
        genre_context += (
            f" They're targeting {fmt} distribution — keep format constraints in mind."
        )

    system_prompt = BRAINSTORM_CONDUCTOR_SYSTEM.format(
        genre_context=genre_context,
    )

    # First message: brainstorm start prompt
    messages = [{"role": "user", "content": BRAINSTORM_START}]

    async def stream_opening():
        """Stream the opening question."""
        full_response = ""
        inside_thought_block = False
        pending_buffer = ""
        max_tag_len = max(len(THOUGHT_OPEN_TAG), len(THOUGHT_CLOSE_TAG))

        try:
            async for token in llm_service.generate_stream(
                system_prompt=system_prompt,
                messages=messages,
                temperature=0.8,
            ):
                full_response += token
                pending_buffer += token

                if inside_thought_block:
                    if THOUGHT_CLOSE_TAG in pending_buffer:
                        inside_thought_block = False
                        pending_buffer = pending_buffer.split(THOUGHT_CLOSE_TAG, 1)[1]
                    elif len(pending_buffer) > len(THOUGHT_CLOSE_TAG):
                        pending_buffer = pending_buffer[-len(THOUGHT_CLOSE_TAG):]
                    continue

                if THOUGHT_OPEN_TAG in pending_buffer:
                    inside_thought_block = True
                    before_tag = pending_buffer.split(THOUGHT_OPEN_TAG, 1)[0]
                    if before_tag:
                        yield f"data: {json.dumps({'type': 'token', 'content': before_tag})}\n\n"
                    pending_buffer = pending_buffer.split(THOUGHT_OPEN_TAG, 1)[1]
                    continue

                if len(pending_buffer) > max_tag_len:
                    safe = pending_buffer[:-max_tag_len]
                    pending_buffer = pending_buffer[-max_tag_len:]
                    yield f"data: {json.dumps({'type': 'token', 'content': safe})}\n\n"

        except Exception as e:
            logger.error("[BRAINSTORM] Stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Brainstorm interrupted — please try again.'})}\n\n"
            return

        if pending_buffer and not inside_thought_block:
            yield f"data: {json.dumps({'type': 'token', 'content': pending_buffer})}\n\n"

        # Clean and store response
        clean_response = re.sub(
            r"<thought_process>.*?</thought_process>", "", full_response, flags=re.DOTALL
        ).strip()
        session.conversation_history.append(
            {"role": "user", "content": BRAINSTORM_START}
        )
        session.conversation_history.append(
            {"role": "assistant", "content": clean_response}
        )
        session.questions_asked = 1

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'questions_asked': 1})}\n\n"

    logger.info("[BRAINSTORM] Started session %s for user %s", session_id, user_id)

    return StreamingResponse(
        stream_opening(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/respond")
async def brainstorm_respond(
    brainstorm_request: BrainstormRespondRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> StreamingResponse:
    """Continue the brainstorming conversation (SSE streaming)."""
    session = get_brainstorm_session(brainstorm_request.session_id, user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brainstorm session not found or expired.",
        )

    # Add user message to history
    session.conversation_history.append(
        {"role": "user", "content": brainstorm_request.message}
    )

    # Build system prompt
    genre_context = ""
    if session.genre:
        genre_context = (
            f"The writer is working in the {session.genre} genre. "
            f"Tailor your questions to genre-specific concerns and conventions."
        )
    if session.distribution_format:
        fmt = session.distribution_format.replace("_", " ")
        genre_context += (
            f" They're targeting {fmt} distribution — keep format constraints in mind."
        )

    system_prompt = BRAINSTORM_CONDUCTOR_SYSTEM.format(
        genre_context=genre_context,
    )

    async def stream_response():
        """Stream the brainstorm response with thought-tag stripping."""
        full_response = ""
        inside_thought_block = False
        pending_buffer = ""
        max_tag_len = max(len(THOUGHT_OPEN_TAG), len(THOUGHT_CLOSE_TAG))

        try:
            async for token in llm_service.generate_stream(
                system_prompt=system_prompt,
                messages=session.conversation_history,
                temperature=0.8,
            ):
                full_response += token
                pending_buffer += token

                if inside_thought_block:
                    if THOUGHT_CLOSE_TAG in pending_buffer:
                        inside_thought_block = False
                        pending_buffer = pending_buffer.split(THOUGHT_CLOSE_TAG, 1)[1]
                    elif len(pending_buffer) > len(THOUGHT_CLOSE_TAG):
                        pending_buffer = pending_buffer[-len(THOUGHT_CLOSE_TAG):]
                    continue

                if THOUGHT_OPEN_TAG in pending_buffer:
                    inside_thought_block = True
                    before_tag = pending_buffer.split(THOUGHT_OPEN_TAG, 1)[0]
                    if before_tag:
                        yield f"data: {json.dumps({'type': 'token', 'content': before_tag})}\n\n"
                    pending_buffer = pending_buffer.split(THOUGHT_OPEN_TAG, 1)[1]
                    continue

                if len(pending_buffer) > max_tag_len:
                    safe = pending_buffer[:-max_tag_len]
                    pending_buffer = pending_buffer[-max_tag_len:]
                    yield f"data: {json.dumps({'type': 'token', 'content': safe})}\n\n"

        except Exception as e:
            logger.error("[BRAINSTORM] Stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Brainstorm interrupted — please try again.'})}\n\n"
            return

        if pending_buffer and not inside_thought_block:
            yield f"data: {json.dumps({'type': 'token', 'content': pending_buffer})}\n\n"

        # Clean and store response
        clean_response = re.sub(
            r"<thought_process>.*?</thought_process>", "", full_response, flags=re.DOTALL
        ).strip()
        session.conversation_history.append(
            {"role": "assistant", "content": clean_response}
        )
        session.questions_asked += 1

        # Background voice refinement — fire-and-forget every N turns.
        # Never block the SSE stream; refine_project_voice_from_brainstorm
        # is itself best-effort and swallows its own errors.
        if (
            session.project_id
            and session.questions_asked > 0
            and session.questions_asked % VOICE_EXTRACTION_INTERVAL == 0
        ):
            asyncio.create_task(
                refine_project_voice_from_brainstorm(
                    project_id=session.project_id,
                    user_id=user_id,
                    conversation_history=list(session.conversation_history),
                )
            )

        yield f"data: {json.dumps({'type': 'done', 'questions_asked': session.questions_asked})}\n\n"

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/evaluate")
async def brainstorm_evaluate(
    evaluate_request: BrainstormEvaluateRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Evaluate the brainstorming session — idea viability gate.

    Compiles the conversation into a structured assessment with scores,
    unresolved questions, and extracted Story Bible entries.
    """
    session = get_brainstorm_session(evaluate_request.session_id, user_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Brainstorm session not found or expired.",
        )

    if not session.conversation_history:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No conversation to evaluate — brainstorm first.",
        )

    # Format conversation for evaluation
    conversation_text = "\n\n".join(
        f"{'WRITER' if m['role'] == 'user' else 'ARCHITECT'}: {m['content']}"
        for m in session.conversation_history
        if m["content"] != BRAINSTORM_START  # Skip internal start prompt
    )

    genre_note = f"\nGENRE: {session.genre}" if session.genre else ""

    eval_prompt = (
        f"Evaluate this brainstorming session:{genre_note}\n\n"
        f"CONVERSATION:\n{conversation_text}\n\n"
        f"Return your evaluation as a JSON object."
    )

    try:
        raw_response = await llm_service.generate(
            system_prompt=EVALUATE_SYSTEM,
            user_prompt=eval_prompt,
            temperature=0.3,
            max_tokens=2000,
        )
    except Exception as e:
        logger.error("[BRAINSTORM] Evaluation failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Evaluation failed — please try again.",
        )

    # Parse evaluation response
    try:
        evaluation = json.loads(raw_response)
    except json.JSONDecodeError:
        # Try extracting JSON from markdown
        json_match = re.search(r"```json?\s*(.*?)\s*```", raw_response, re.DOTALL)
        if json_match:
            evaluation = json.loads(json_match.group(1))
        else:
            # Try finding JSON object
            start = raw_response.index("{")
            end = raw_response.rindex("}") + 1
            evaluation = json.loads(raw_response[start:end])

    logger.info(
        "[BRAINSTORM] Evaluated session %s: premise=%s, stakes=%s, conflict=%s",
        session.session_id,
        evaluation.get("premise_clarity"),
        evaluation.get("stakes_strength"),
        evaluation.get("conflict_depth"),
    )

    return {
        "evaluation": evaluation,
        "session_id": session.session_id,
        "questions_asked": session.questions_asked,
    }
