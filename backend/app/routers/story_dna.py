"""Story DNA Analyzer router — anonymous personality interview + concepts.

Phase 2 of the Layer 1 reconcile. Anonymous, no auth, IP rate-limited
to 3 sessions per IP per 24 hours. Sessions live in memory for 2 hours
so the user can complete signup and migrate the session afterwards
(migration endpoints land in Phase 3).
"""

import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.models.story_dna_session import (
    check_rate_limit,
    create_session,
    get_session,
)
from app.prompts.story_dna_conductor import (
    STORY_DNA_CONDUCTOR_OPENING_USER,
    STORY_DNA_CONDUCTOR_SYSTEM,
)
from app.services import llm_service
from app.services.story_dna_service import synthesize_dna

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/story-dna", tags=["story-dna"])

DNA_COMPLETE_SIGNAL = "[DNA_ANALYSIS_COMPLETE]"
MAX_QUESTIONS = 7


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class StartResponse(BaseModel):
    session_id: str
    first_question: str
    question_count: int


class RespondRequest(BaseModel):
    session_id: str
    answer: str


class FinalizeRequest(BaseModel):
    session_id: str


class FinalizeResponse(BaseModel):
    session_id: str
    story_dna_profile: dict
    concepts: list[dict]
    cta_paywall: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str:
    """Best-effort client IP. Honors X-Forwarded-For for Railway proxy."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _generate_assistant_turn(turns: list[dict[str, str]]) -> str:
    """Run the conductor for one assistant turn (non-streaming)."""
    chunks: list[str] = []
    async for token in llm_service.generate_stream(
        system_prompt=STORY_DNA_CONDUCTOR_SYSTEM,
        messages=turns,
        temperature=0.8,
    ):
        chunks.append(token)
    return "".join(chunks)


# ---------------------------------------------------------------------------
# 1. Start session
# ---------------------------------------------------------------------------


@router.post("/start", response_model=StartResponse)
async def start_dna_session(request: Request) -> StartResponse:
    """Create a new anonymous Story DNA session and return the first question."""
    ip = _client_ip(request)

    if not check_rate_limit(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You've reached the daily limit for the Story DNA test. Try again tomorrow.",
        )

    session = create_session(ip=ip)

    # Seed the conductor with the opening user message and capture the welcome question
    seed_turns = [{"role": "user", "content": STORY_DNA_CONDUCTOR_OPENING_USER}]
    try:
        first_message = await _generate_assistant_turn(seed_turns)
    except Exception as e:
        logger.error("[STORY_DNA] failed to generate opening question: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not start the Story DNA test — please try again.",
        )

    first_message = first_message.strip()
    session.turns.append({"role": "assistant", "content": first_message})
    session.question_count = 1

    return StartResponse(
        session_id=session.session_id,
        first_question=first_message,
        question_count=session.question_count,
    )


# ---------------------------------------------------------------------------
# 2. Respond (SSE stream of next question)
# ---------------------------------------------------------------------------


@router.post("/respond")
async def respond_to_question(payload: RespondRequest) -> StreamingResponse:
    """Stream the next conductor question via SSE.

    The user's answer is appended to the session, then the conductor is
    asked for its next turn. Strips [DNA_ANALYSIS_COMPLETE] before
    streaming and signals completion in the final SSE `done` event.
    """
    session = get_session(payload.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Your Story DNA session expired. Please retake the test.",
        )
    if session.finalized:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This session is already complete.",
        )

    answer = (payload.answer or "").strip()
    if not answer:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please provide an answer.",
        )

    session.turns.append({"role": "user", "content": answer})

    async def stream() -> ...:
        full_response = ""
        pending_buffer = ""
        signal_len = len(DNA_COMPLETE_SIGNAL)
        complete = False

        try:
            async for token in llm_service.generate_stream(
                system_prompt=STORY_DNA_CONDUCTOR_SYSTEM,
                messages=session.turns,
                temperature=0.8,
            ):
                full_response += token
                pending_buffer += token

                if DNA_COMPLETE_SIGNAL in pending_buffer:
                    complete = True
                    before = pending_buffer.split(DNA_COMPLETE_SIGNAL)[0]
                    if before:
                        yield f"data: {json.dumps({'type': 'token', 'content': before})}\n\n"
                    pending_buffer = ""
                    continue

                if len(pending_buffer) > signal_len:
                    safe = pending_buffer[:-signal_len]
                    pending_buffer = pending_buffer[-signal_len:]
                    yield f"data: {json.dumps({'type': 'token', 'content': safe})}\n\n"

        except Exception as e:
            logger.error("[STORY_DNA] respond stream error: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'content': 'Story DNA interrupted — please try again.'})}\n\n"
            return

        if pending_buffer and not complete:
            yield f"data: {json.dumps({'type': 'token', 'content': pending_buffer})}\n\n"

        clean = full_response.replace(DNA_COMPLETE_SIGNAL, "").strip()
        session.turns.append({"role": "assistant", "content": clean})
        session.question_count += 1

        # Hard cap: force completion at MAX_QUESTIONS even if conductor didn't signal
        if session.question_count >= MAX_QUESTIONS:
            complete = True

        if complete:
            session.finalized = False  # finalize() endpoint flips this after synthesis
            ready_for_finalize = True
        else:
            ready_for_finalize = False

        yield (
            "data: "
            + json.dumps(
                {
                    "type": "done",
                    "ready_for_finalize": ready_for_finalize,
                    "question_count": session.question_count,
                }
            )
            + "\n\n"
        )

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 3. Finalize — synthesize DNA profile + concepts
# ---------------------------------------------------------------------------


@router.post("/finalize", response_model=FinalizeResponse)
async def finalize_dna_session(payload: FinalizeRequest) -> FinalizeResponse:
    """Synthesize the Story DNA Profile and concepts from the session turns.

    Stores the result on the session (still in memory under the 2-hour TTL)
    so a downstream migrate-session call can persist it after signup.
    """
    session = get_session(payload.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Your Story DNA session expired. Please retake the test.",
        )

    # Idempotent: if already finalized, return the cached result
    if session.finalized and session.dna_profile and session.concepts is not None:
        return FinalizeResponse(
            session_id=session.session_id,
            story_dna_profile=session.dna_profile,
            concepts=session.concepts,
            cta_paywall="Pick a concept and build it into a novel with BUB Writer",
        )

    answered = sum(1 for t in session.turns if t["role"] == "user")
    if answered < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please answer a few more questions before finalizing.",
        )

    try:
        profile, concepts = await synthesize_dna(session.turns)
    except Exception as e:
        logger.error("[STORY_DNA] finalize synthesis failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate your Story DNA — please try again.",
        )

    session.dna_profile = profile
    session.concepts = concepts
    session.voice_signal = profile.get("voice_signal")
    session.finalized = True

    return FinalizeResponse(
        session_id=session.session_id,
        story_dna_profile=profile,
        concepts=concepts,
        cta_paywall="Pick a concept and build it into a novel with BUB Writer",
    )
