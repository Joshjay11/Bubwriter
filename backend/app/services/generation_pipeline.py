"""Generation pipeline orchestrator — Brain -> Voice -> Polish.

The core engine that runs all three stages and yields SSE events.
Handles quality gates, graceful degradation, and two-phase DB storage.
"""

import json
import logging
from collections.abc import AsyncGenerator

from pydantic import ValidationError

from app.models.generation_schemas import SceneSkeleton
from app.services.anti_slop import build_anti_slop_block
from app.services.brain_service import run_brain
from app.services.polish_service import run_polish
from app.services.supabase_client import get_supabase_client
from app.services.voice_service import format_skeleton_for_voice, stream_voice

logger = logging.getLogger(__name__)


# --- SSE Event Helpers ---

def sse_event(event_type: str, **kwargs: object) -> str:
    """Format a single SSE event line."""
    payload = {"type": event_type, **kwargs}
    return f"data: {json.dumps(payload)}\n\n"


# --- Story Context Builders ---

def build_story_context(project: dict | None) -> str:
    """Extract story context from a project's story_bible."""
    if not project:
        return ""

    story_bible = project.get("story_bible", {})
    if not story_bible:
        return f"Project: {project.get('title', 'Untitled')}"

    lines = [f"Project: {project.get('title', 'Untitled')}"]
    if project.get("genre"):
        lines.append(f"Genre: {project['genre']}")

    for key, value in story_bible.items():
        if value:
            lines.append(f"{key}: {value}")

    return "\n".join(lines)


def build_continuation_context(previous_output: str) -> str:
    """Build continuation context from previous scene output.

    Includes the last ~1000 words to give R1 narrative momentum
    without overwhelming the context window.
    """
    words = previous_output.split()
    if len(words) > 1000:
        truncated = " ".join(words[-1000:])
        return f"[...previous scene continues...]\n\n{truncated}"
    return previous_output


# --- Quality Gate ---

def validate_skeleton(skeleton_json: str) -> SceneSkeleton | None:
    """Validate Brain output meets quality thresholds.

    Tier 1: Valid JSON + schema match
    Tier 2: At least 3 beats, 2 distinct emotional tones
    Returns None if validation fails (caller handles fallback).
    """
    try:
        validated = SceneSkeleton.model_validate_json(skeleton_json)
    except (ValidationError, ValueError):
        return None

    # Tier 2: programmatic checks
    if len(validated.beats) < 3:
        logger.warning("[GENERATION] Skeleton has fewer than 3 beats")
        return None

    tones = {b.emotional_tone.lower() for b in validated.beats if b.emotional_tone}
    if len(tones) < 2:
        logger.warning("[GENERATION] Skeleton has fewer than 2 distinct emotional tones")
        # Still usable — just log the warning
        pass

    return validated


# --- Two-Phase DB Storage ---

async def store_generation_after_brain(
    user_id: str,
    project_id: str | None,
    user_prompt: str,
    brain_output: str,
) -> str:
    """Phase 1: Insert generation row after Brain completes.

    voice_output is empty — updated after Voice finishes.
    This enables 'Regenerate' to skip Brain and reuse the skeleton.
    """
    supabase = get_supabase_client()
    insert_data: dict = {
        "user_id": user_id,
        "user_prompt": user_prompt,
        "brain_output": brain_output,
        "voice_output": "",
        "word_count": 0,
    }
    if project_id:
        insert_data["project_id"] = project_id

    result = supabase.table("generations").insert(insert_data).execute()
    generation_id = result.data[0]["id"]
    logger.info("[GENERATION] Stored brain output, generation_id=%s", generation_id)
    return generation_id


async def update_generation_after_voice(
    generation_id: str,
    voice_output: str,
    polish_output: str | None,
    word_count: int,
) -> None:
    """Phase 2: Update generation row after Voice (and optional Polish) complete."""
    supabase = get_supabase_client()
    update_data: dict = {
        "voice_output": voice_output,
        "word_count": word_count,
    }
    if polish_output is not None:
        update_data["polish_output"] = polish_output

    supabase.table("generations").update(update_data).eq("id", generation_id).execute()
    logger.info(
        "[GENERATION] Updated generation %s: %d words", generation_id, word_count
    )


# --- Main Pipeline ---

async def run_generation_pipeline(
    user_id: str,
    prompt: str,
    voice_instruction: str,
    anti_slop: dict | None,
    project: dict | None,
    include_polish: bool,
    previous_output: str | None,
) -> AsyncGenerator[str, None]:
    """The Brain -> Voice -> Polish pipeline.

    Yields SSE events as the pipeline progresses.
    """

    # ─── STAGE 1: THE BRAIN ─────────────────────────────────
    yield sse_event("stage", stage="brain", message="Designing scene structure...")

    story_context = build_story_context(project)
    continuation_context = (
        build_continuation_context(previous_output) if previous_output else ""
    )

    try:
        skeleton_json = await run_brain(
            prompt=prompt,
            story_context=story_context,
            continuation_context=continuation_context,
        )
    except Exception as e:
        logger.error("[GENERATION] Brain stage failed: %s", e)
        yield sse_event("error", content=f"Scene structure generation failed: {e}")
        return

    # Quality gate — validate the skeleton
    validated = validate_skeleton(skeleton_json)
    if validated is None:
        # Retry once with tighter constraints
        yield sse_event("stage", stage="brain", message="Refining structure...")
        try:
            skeleton_json = await run_brain(
                prompt=prompt,
                story_context=story_context,
                continuation_context=continuation_context,
                retry=True,
            )
            validated = validate_skeleton(skeleton_json)
        except Exception as e:
            logger.warning("[GENERATION] Brain retry failed: %s", e)
            # Fall through — validated stays None, raw text goes to Voice

    yield sse_event("skeleton", data=skeleton_json)

    # ─── EARLY INSERT: Store generation with brain_output ────
    try:
        generation_id = await store_generation_after_brain(
            user_id=user_id,
            project_id=project.get("id") if project else None,
            user_prompt=prompt,
            brain_output=skeleton_json,
        )
    except Exception as e:
        logger.error("[GENERATION] Failed to store brain output: %s", e)
        yield sse_event("error", content="Failed to save generation progress.")
        return

    # ─── STAGE 2: THE VOICE ─────────────────────────────────
    yield sse_event("stage", stage="voice", message="Writing in your voice...")

    anti_slop_rules = build_anti_slop_block(anti_slop)
    readable_skeleton = format_skeleton_for_voice(validated or skeleton_json)
    target_word_count = validated.target_word_count if validated else 2000

    full_output = ""
    try:
        async for token in stream_voice(
            skeleton=readable_skeleton,
            voice_instruction=voice_instruction,
            anti_slop_rules=anti_slop_rules,
            story_context=story_context,
            target_word_count=target_word_count,
        ):
            full_output += token
            yield sse_event("token", content=token)
    except Exception as e:
        logger.error("[GENERATION] Voice stage failed: %s", e)
        yield sse_event("error", content=f"Prose generation failed: {e}")
        # Still try to save whatever we got
        if full_output:
            await update_generation_after_voice(
                generation_id=generation_id,
                voice_output=full_output,
                polish_output=None,
                word_count=len(full_output.split()),
            )
        return

    word_count = len(full_output.split())

    if not full_output.strip():
        yield sse_event("error", content="Voice model returned empty output.")
        return

    # ─── STAGE 3: THE POLISH (Author tier only) ─────────────
    polished_output = None
    if include_polish:
        yield sse_event("stage", stage="polish", message="Polishing your prose...")
        try:
            polished_output = await run_polish(
                prose=full_output,
                voice_instruction=voice_instruction,
                anti_slop_rules=anti_slop_rules,
            )
            yield sse_event("polish_complete", content=polished_output)
            word_count = len(polished_output.split())
        except Exception as e:
            logger.error("[GENERATION] Polish stage failed: %s", e)
            # Polish failure is non-fatal — user still gets Voice output
            yield sse_event(
                "stage", stage="polish", message="Polish unavailable — using original."
            )

    # ─── UPDATE GENERATION with Voice + Polish output ────────
    try:
        await update_generation_after_voice(
            generation_id=generation_id,
            voice_output=full_output,
            polish_output=polished_output,
            word_count=word_count,
        )
    except Exception as e:
        logger.error("[GENERATION] Failed to update generation: %s", e)
        # Non-fatal — the user still saw the output

    yield sse_event("done", metadata={
        "word_count": word_count,
        "generation_id": generation_id,
    })


# --- Refine Pipeline (Voice-only with feedback) ---

async def run_refine_pipeline(
    user_id: str,
    generation_id: str,
    feedback: str,
    voice_instruction: str,
    anti_slop: dict | None,
    include_polish: bool,
) -> AsyncGenerator[str, None]:
    """Re-run Voice with user feedback, reusing the Brain skeleton.

    Loads the stored brain_output from the existing generation,
    appends user feedback as additional instructions to Voice.
    Creates a new generation row (preserves the original).
    """
    # Load existing generation
    supabase = get_supabase_client()
    result = (
        supabase.table("generations")
        .select("brain_output, user_prompt, project_id")
        .eq("id", generation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        yield sse_event("error", content="Generation not found.")
        return

    gen = result.data[0]
    skeleton_json = gen["brain_output"]
    user_prompt = gen["user_prompt"]
    project_id = gen.get("project_id")

    # Validate skeleton if possible
    validated = validate_skeleton(skeleton_json)
    readable_skeleton = format_skeleton_for_voice(validated or skeleton_json)

    # Store new generation with same skeleton
    try:
        new_gen_id = await store_generation_after_brain(
            user_id=user_id,
            project_id=project_id,
            user_prompt=user_prompt,
            brain_output=skeleton_json,
        )
    except Exception as e:
        logger.error("[GENERATION] Failed to store refine generation: %s", e)
        yield sse_event("error", content="Failed to save generation.")
        return

    # Voice stage with feedback
    yield sse_event("stage", stage="voice", message="Rewriting with your feedback...")

    anti_slop_rules = build_anti_slop_block(anti_slop)
    target_word_count = validated.target_word_count if validated else 2000

    full_output = ""
    try:
        async for token in stream_voice(
            skeleton=readable_skeleton,
            voice_instruction=voice_instruction,
            anti_slop_rules=anti_slop_rules,
            story_context="",
            target_word_count=target_word_count,
            additional_instructions=f"USER FEEDBACK on previous draft: {feedback}",
        ):
            full_output += token
            yield sse_event("token", content=token)
    except Exception as e:
        logger.error("[GENERATION] Refine voice failed: %s", e)
        yield sse_event("error", content=f"Prose generation failed: {e}")
        return

    word_count = len(full_output.split())

    # Optional polish
    polished_output = None
    if include_polish:
        yield sse_event("stage", stage="polish", message="Polishing your prose...")
        try:
            polished_output = await run_polish(
                prose=full_output,
                voice_instruction=voice_instruction,
                anti_slop_rules=anti_slop_rules,
            )
            yield sse_event("polish_complete", content=polished_output)
            word_count = len(polished_output.split())
        except Exception as e:
            logger.error("[GENERATION] Refine polish failed: %s", e)

    # Update DB
    try:
        await update_generation_after_voice(
            generation_id=new_gen_id,
            voice_output=full_output,
            polish_output=polished_output,
            word_count=word_count,
        )
    except Exception as e:
        logger.error("[GENERATION] Failed to update refine generation: %s", e)

    yield sse_event("done", metadata={
        "word_count": word_count,
        "generation_id": new_gen_id,
    })
