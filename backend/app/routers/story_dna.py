"""Story DNA Analyzer router — anonymous personality interview + concepts.

Phase 2 of the Layer 1 reconcile. Anonymous, no auth, IP rate-limited
to 3 sessions per IP per 24 hours. Sessions live in memory for 2 hours
so the user can complete signup and migrate the session afterwards
(migration endpoints land in Phase 3).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
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
from app.services.supabase_client import get_supabase_client

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


class MigrateSessionRequest(BaseModel):
    session_id: str
    profile_name: str | None = None


class MigrateSessionResponse(BaseModel):
    dna_profile_id: str
    status: str


class CreateProjectFromDnaRequest(BaseModel):
    dna_profile_id: str
    concept_id: str
    project_title: str | None = None


class CreateProjectFromDnaResponse(BaseModel):
    project_id: str
    voice_profile_id: str


class DnaProfileListItem(BaseModel):
    id: str
    profile_name: str | None
    dna_profile: dict
    concept_count: int
    projects_created_count: int
    created_at: str


class DnaProfileDetail(BaseModel):
    id: str
    profile_name: str | None
    dna_profile: dict
    concepts: list[dict]
    session_turns: list[dict]
    created_at: str
    updated_at: str


class RegenerateConceptsResponse(BaseModel):
    concepts: list[dict]


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


# ---------------------------------------------------------------------------
# 4. Migrate anonymous session → persistent storage (auth required)
# ---------------------------------------------------------------------------


def _default_profile_name() -> str:
    return f"Story DNA — {datetime.now(timezone.utc).strftime('%B %d, %Y')}"


@router.post("/migrate-session", response_model=MigrateSessionResponse)
async def migrate_session(
    payload: MigrateSessionRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> MigrateSessionResponse:
    """Persist a finalized anonymous session to story_dna_profiles.

    Idempotent per (session, user): re-calling returns the existing
    dna_profile_id rather than creating a duplicate row.
    """
    session = get_session(payload.session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired — please retake the DNA test.",
        )
    if not session.finalized or not session.dna_profile or session.concepts is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session not yet finalized.",
        )

    # Idempotency — same user re-calling gets the same profile id back
    existing_id = session.migrated_user_ids.get(user_id)
    if existing_id:
        return MigrateSessionResponse(dna_profile_id=existing_id, status="already_migrated")

    profile_name = payload.profile_name or _default_profile_name()

    supabase = get_supabase_client()
    insert_data = {
        "user_id": user_id,
        "profile_name": profile_name,
        "dna_profile": session.dna_profile,
        "session_turns": session.turns,
        "concepts": session.concepts,
    }

    try:
        result = supabase.table("story_dna_profiles").insert(insert_data).execute()
        dna_profile_id = result.data[0]["id"]
    except Exception as e:
        logger.error("[STORY_DNA] migrate-session insert failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save your Story DNA profile — please try again.",
        )

    session.migrated_user_ids[user_id] = dna_profile_id
    logger.info("[STORY_DNA] migrated session %s → profile %s for user %s", session.session_id, dna_profile_id, user_id)

    return MigrateSessionResponse(dna_profile_id=dna_profile_id, status="migrated")


# ---------------------------------------------------------------------------
# 5. Create project from persistent DNA profile (auth required)
# ---------------------------------------------------------------------------


def _build_voice_instruction_from_signal(voice_signal: dict) -> str:
    """Cheap, deterministic compiler — turns a voice_signal dict into a
    plain-text starter system prompt for downstream Voice generation.

    This is a starter, NOT a finished Voice DNA Profile. It will be
    refined in the background as the user brainstorms (Phase 5).
    """
    if not voice_signal:
        return (
            "You are the writer. Write in a natural, grounded prose voice. "
            "Show, don't tell. Trust the reader. Avoid cliché."
        )

    vocab = voice_signal.get("vocabulary_tier") or "conversational"
    rhythm = voice_signal.get("sentence_rhythm") or "balanced"
    sensory = voice_signal.get("sensory_bias") or "mixed"
    temp = voice_signal.get("emotional_temperature") or "measured"
    humor = voice_signal.get("humor_presence") or "none"
    notes = voice_signal.get("notes") or ""

    parts = [
        "You are the writer. This is a starter voice — it will sharpen as the writer keeps working with BUB Writer.",
        "",
        "VOICE SIGNATURE",
        f"- Vocabulary: {vocab}",
        f"- Sentence rhythm: {rhythm}",
        f"- Sensory bias: {sensory} detail",
        f"- Emotional temperature: {temp}",
        f"- Humor: {humor}",
    ]
    if notes:
        parts.append(f"- Notes: {notes}")
    parts.extend(
        [
            "",
            "RULES",
            "- Match the rhythm and vocabulary tier above. Do not drift into generic literary register.",
            "- Lead with the sensory bias when grounding scenes.",
            "- Show, don't tell. Trust the reader.",
            "- Avoid cliché, throat-clearing, and writerly filler.",
        ]
    )
    return "\n".join(parts)


def _literary_dna_from_signal(voice_signal: dict) -> dict:
    """Map a voice_signal dict onto the LiteraryDNA-shaped JSON we store."""
    if not voice_signal:
        return {}
    return {
        "vocabulary_tier": voice_signal.get("vocabulary_tier"),
        "sentence_rhythm": voice_signal.get("sentence_rhythm"),
        "sensory_mode": voice_signal.get("sensory_bias"),
        "emotional_register": voice_signal.get("emotional_temperature"),
        "humor_style": voice_signal.get("humor_presence"),
        "notable_patterns": [voice_signal["notes"]] if voice_signal.get("notes") else [],
    }


@router.post("/create-project", response_model=CreateProjectFromDnaResponse)
async def create_project_from_dna(
    payload: CreateProjectFromDnaRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> CreateProjectFromDnaResponse:
    """Create a new project + starter voice profile from a persistent DNA profile.

    1. Loads the dna profile row (RLS-enforced ownership via user_id filter).
    2. Finds the chosen concept by concept_id.
    3. Creates a starter voice_profiles row with profile_source='dna_analyzer'.
    4. Creates the projects row, pre-populated with concept context and the
       new voice profile id.
    """
    supabase = get_supabase_client()

    # 1. Load DNA profile (RLS + explicit user_id filter for safety)
    try:
        dna_result = (
            supabase.table("story_dna_profiles")
            .select("*")
            .eq("id", payload.dna_profile_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        logger.error("[STORY_DNA] failed to load dna profile: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load your Story DNA profile.",
        )

    if not dna_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story DNA profile not found.",
        )

    dna_row = dna_result.data[0]
    dna_profile = dna_row.get("dna_profile") or {}
    concepts = dna_row.get("concepts") or []

    # 2. Locate chosen concept
    concept = next((c for c in concepts if c.get("concept_id") == payload.concept_id), None)
    if concept is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Concept not found in this Story DNA profile.",
        )

    voice_signal = dna_profile.get("voice_signal") or {}

    # 3. Create starter voice profile
    voice_insert = {
        "user_id": user_id,
        "profile_name": "From your Story DNA session",
        "literary_dna": _literary_dna_from_signal(voice_signal),
        "influences": {},
        "anti_slop": {},
        "voice_instruction": _build_voice_instruction_from_signal(voice_signal),
        "voice_summary": dna_profile.get("genre_sweet_spot") or "",
        "profile_source": "dna_analyzer",
    }
    try:
        vp_result = supabase.table("voice_profiles").insert(voice_insert).execute()
        voice_profile_id = vp_result.data[0]["id"]
    except Exception as e:
        logger.error("[STORY_DNA] starter voice profile insert failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create your starter voice profile.",
        )

    # 4. Create project
    project_insert = {
        "user_id": user_id,
        "title": payload.project_title or concept.get("working_title") or "Untitled",
        "genre": concept.get("genre"),
        "distribution_format": concept.get("distribution_format"),
        "voice_profile_id": voice_profile_id,
        "story_bible": {
            "concept_origin": concept,
            "story_dna_profile_ref": {
                "dna_profile_id": payload.dna_profile_id,
                "used_concept_id": payload.concept_id,
            },
        },
    }
    try:
        proj_result = supabase.table("projects").insert(project_insert).execute()
        project_id = proj_result.data[0]["id"]
    except Exception as e:
        logger.error("[STORY_DNA] project insert failed: %s", e)
        # Best-effort cleanup of the orphan voice profile
        try:
            supabase.table("voice_profiles").delete().eq("id", voice_profile_id).execute()
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create your project.",
        )

    logger.info("[STORY_DNA] created project %s + voice profile %s from dna %s", project_id, voice_profile_id, payload.dna_profile_id)

    return CreateProjectFromDnaResponse(
        project_id=project_id,
        voice_profile_id=voice_profile_id,
    )


# ---------------------------------------------------------------------------
# 6. Persistent DNA profile management (auth required)
# ---------------------------------------------------------------------------


def _load_dna_profile_row(profile_id: str, user_id: str) -> dict:
    """Load a story_dna_profiles row, enforcing ownership. 404 if missing."""
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("story_dna_profiles")
            .select("*")
            .eq("id", profile_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        logger.error("[STORY_DNA] failed to load profile %s: %s", profile_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load Story DNA profile.",
        )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story DNA profile not found.",
        )
    return result.data[0]


@router.get("/profiles", response_model=list[DnaProfileListItem])
async def list_dna_profiles(
    user_id: Annotated[str, Depends(get_current_user)],
) -> list[DnaProfileListItem]:
    """List all persistent Story DNA profiles for the authenticated user."""
    supabase = get_supabase_client()

    try:
        result = (
            supabase.table("story_dna_profiles")
            .select("id, profile_name, dna_profile, concepts, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
    except Exception as e:
        logger.error("[STORY_DNA] list profiles failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not load your Story DNA profiles.",
        )

    rows = result.data or []
    if not rows:
        return []

    # Batch-fetch project counts grouped by story_dna_profile_ref.dna_profile_id
    # We can't easily group on a JSONB path through the supabase-py client, so
    # fetch all this user's projects with a story_dna ref and tally in Python.
    project_counts: dict[str, int] = {}
    try:
        proj_result = (
            supabase.table("projects")
            .select("story_bible")
            .eq("user_id", user_id)
            .execute()
        )
        for p in proj_result.data or []:
            ref = (p.get("story_bible") or {}).get("story_dna_profile_ref") or {}
            ref_id = ref.get("dna_profile_id")
            if ref_id:
                project_counts[ref_id] = project_counts.get(ref_id, 0) + 1
    except Exception as e:
        logger.warning("[STORY_DNA] project count tally failed: %s", e)

    items: list[DnaProfileListItem] = []
    for row in rows:
        items.append(
            DnaProfileListItem(
                id=row["id"],
                profile_name=row.get("profile_name"),
                dna_profile=row.get("dna_profile") or {},
                concept_count=len(row.get("concepts") or []),
                projects_created_count=project_counts.get(row["id"], 0),
                created_at=row["created_at"],
            )
        )
    return items


@router.get("/profiles/{dna_profile_id}", response_model=DnaProfileDetail)
async def get_dna_profile(
    dna_profile_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> DnaProfileDetail:
    """Get a single persistent Story DNA profile in full."""
    row = _load_dna_profile_row(dna_profile_id, user_id)
    return DnaProfileDetail(
        id=row["id"],
        profile_name=row.get("profile_name"),
        dna_profile=row.get("dna_profile") or {},
        concepts=row.get("concepts") or [],
        session_turns=row.get("session_turns") or [],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.delete("/profiles/{dna_profile_id}")
async def delete_dna_profile(
    dna_profile_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict[str, bool]:
    """Delete a persistent Story DNA profile.

    Projects already created from this DNA are NOT touched — they keep
    their concept_origin in story_bible and continue to function.
    """
    _load_dna_profile_row(dna_profile_id, user_id)
    supabase = get_supabase_client()
    try:
        supabase.table("story_dna_profiles").delete().eq("id", dna_profile_id).eq("user_id", user_id).execute()
    except Exception as e:
        logger.error("[STORY_DNA] delete profile %s failed: %s", dna_profile_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete Story DNA profile.",
        )
    logger.info("[STORY_DNA] deleted profile %s for user %s", dna_profile_id, user_id)
    return {"deleted": True}


@router.post(
    "/profiles/{dna_profile_id}/regenerate-concepts",
    response_model=RegenerateConceptsResponse,
)
async def regenerate_concepts(
    dna_profile_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> RegenerateConceptsResponse:
    """Re-run the concept generator against the stored session turns.

    Appends the new concepts to the existing concepts array (with a fresh
    generation timestamp on each new concept) so previously-saved concepts
    are preserved. Concept IDs are kept unique across the full array.
    """
    row = _load_dna_profile_row(dna_profile_id, user_id)
    session_turns = row.get("session_turns") or []
    if not session_turns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This Story DNA profile has no session transcript to regenerate from.",
        )

    try:
        _, new_concepts = await synthesize_dna(session_turns)
    except Exception as e:
        logger.error("[STORY_DNA] regenerate-concepts synthesis failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate new concepts — please try again.",
        )

    existing_concepts = row.get("concepts") or []
    used_ids = {c.get("concept_id") for c in existing_concepts}
    next_index = len(existing_concepts) + 1
    generated_at = datetime.now(timezone.utc).isoformat()

    appended: list[dict] = []
    for c in new_concepts:
        # Always assign a fresh sequential id to avoid collisions with
        # earlier generations — concept_001 may already exist.
        while True:
            new_id = f"concept_{next_index:03d}"
            next_index += 1
            if new_id not in used_ids:
                used_ids.add(new_id)
                break
        c["concept_id"] = new_id
        c["generated_at"] = generated_at
        appended.append(c)

    merged = existing_concepts + appended

    supabase = get_supabase_client()
    try:
        supabase.table("story_dna_profiles").update(
            {
                "concepts": merged,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", dna_profile_id).eq("user_id", user_id).execute()
    except Exception as e:
        logger.error("[STORY_DNA] regenerate-concepts persist failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not save the new concepts — please try again.",
        )

    logger.info("[STORY_DNA] regenerated %d concepts for profile %s", len(appended), dna_profile_id)
    return RegenerateConceptsResponse(concepts=appended)
