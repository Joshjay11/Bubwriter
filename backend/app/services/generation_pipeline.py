"""Generation pipeline orchestrator — Brain -> Voice -> Polish.

The core engine that runs all three stages and yields SSE events.
Handles quality gates, graceful degradation, and two-phase DB storage.
"""

import json
import logging
from collections.abc import AsyncGenerator

from pydantic import ValidationError

from app.core.features import is_enabled
from app.services.genre_guardrails import build_genre_guardrails
from app.models.generation_schemas import SceneSkeleton, VoiceMode
from app.services.anti_slop import build_anti_slop_block
from app.services.brain_service import run_brain
from app.services.extraction_service import extract_story_facts
from app.services.polish_service import run_polish
from app.services.slop_validator import slop_validator
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
    """Extract story context from a project's story_bible.

    Includes POV-aware knowledge constraints from story_secrets.
    """
    if not project:
        return ""

    story_bible = project.get("story_bible", {})
    if not story_bible:
        return f"Project: {project.get('title', 'Untitled')}"

    lines = [f"Project: {project.get('title', 'Untitled')}"]
    if project.get("genre"):
        lines.append(f"Genre: {project['genre']}")

    # Standard bible entries (skip structured sections handled below)
    structured_sections = {"characters", "locations", "world_rules", "plot_beats",
                           "story_secrets", "character_updates", "character_states",
                           "timeline", "object_states", "outline"}
    for key, value in story_bible.items():
        if key in structured_sections:
            continue
        if value:
            lines.append(f"{key}: {value}")

    # Format characters with knowledge
    characters = story_bible.get("characters", [])
    if characters:
        lines.append("\nCHARACTERS:")
        for c in characters:
            role = c.get("role", "")
            desc = c.get("description", "")
            char_line = f"- {c.get('name', 'unnamed')}"
            if role:
                char_line += f" ({role})"
            if desc:
                char_line += f": {desc}"
            lines.append(char_line)

    # Format locations
    locations = story_bible.get("locations", [])
    if locations:
        lines.append("\nLOCATIONS:")
        for loc in locations:
            lines.append(f"- {loc.get('name', 'unnamed')}: {loc.get('description', '')}")

    # Format world rules
    world_rules = story_bible.get("world_rules", [])
    if world_rules:
        lines.append("\nWORLD RULES:")
        for r in world_rules:
            lines.append(f"- [{r.get('category', '')}] {r.get('rule', '')}")

    # Knowledge constraints — POV-aware secrets
    secrets = story_bible.get("story_secrets", [])
    if secrets:
        secret_lines = []
        for s in secrets:
            who_knows = ", ".join(s.get("characters_who_know", []))
            who_doesnt = ", ".join(s.get("characters_who_dont_know", []))
            secret_lines.append(
                f"- SECRET: {s.get('summary', '')}\n"
                f"  Known by: {who_knows or 'no one yet'}\n"
                f"  Unknown to: {who_doesnt or 'n/a'}"
            )
        lines.append(
            "\nINFORMATION ASYMMETRY (POV CONSTRAINTS):\n"
            + "\n".join(secret_lines)
            + "\n\nCRITICAL: Characters cannot act on or reference information "
            "they don't know. Any suspicious behavior must be motivated by "
            "on-page evidence only."
        )

    # Timeline context
    timeline = story_bible.get("timeline", [])
    if timeline:
        lines.append("\nTIMELINE (recent events):")
        # Show last 10 events to avoid context bloat
        for t in timeline[-10:]:
            chars = ", ".join(t.get("characters_present", []))
            when = t.get("when", "?")
            lines.append(f"- [{when}] {t.get('event', '')}")
            if chars:
                lines.append(f"  Present: {chars}")

    # Active character states (injuries, emotional states)
    char_states = story_bible.get("character_states", [])
    active_states = [s for s in char_states if s.get("status") == "active"]
    if active_states:
        lines.append("\nACTIVE CHARACTER STATES:")
        for s in active_states:
            lines.append(
                f"- {s.get('character_id', '?')} [{s.get('state_type', '')}]: "
                f"{s.get('description', '')}"
            )
        lines.append(
            "\nIMPORTANT: Active injuries and physical states must be reflected "
            "in character behavior. A character with broken ribs cannot sprint. "
            "A character who hasn't slept in two days shows fatigue."
        )

    # Object states
    obj_states = story_bible.get("object_states", [])
    if obj_states:
        lines.append("\nOBJECT STATES:")
        for o in obj_states:
            lines.append(
                f"- {o.get('object_name', '?')}: {o.get('current_state', '')}"
            )

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
    voice_mode: VoiceMode = VoiceMode.default,
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
        "voice_mode": voice_mode.value,
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
    voice_mode: VoiceMode = VoiceMode.default,
    voice_model: str | None = None,
) -> AsyncGenerator[str, None]:
    """The Brain -> Voice -> Polish pipeline.

    Yields SSE events as the pipeline progresses.
    If voice_model is set (from profile), it overrides voice_mode for routing.
    """

    # ─── STAGE 1: THE BRAIN ─────────────────────────────────
    yield sse_event("stage", stage="brain", message="Designing scene structure...")

    story_context = build_story_context(project)
    continuation_context = (
        build_continuation_context(previous_output) if previous_output else ""
    )
    genre_guardrails = ""
    if project:
        genre_guardrails = build_genre_guardrails(
            genre=project.get("genre"),
            distribution_format=project.get("distribution_format"),
        )

    try:
        skeleton_json = await run_brain(
            prompt=prompt,
            story_context=story_context,
            continuation_context=continuation_context,
            genre_guardrails=genre_guardrails,
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
                genre_guardrails=genre_guardrails,
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
            voice_mode=voice_mode,
        )
    except Exception as e:
        logger.error("[GENERATION] Failed to store brain output: %s", e)
        yield sse_event("error", content="Failed to save generation progress.")
        return

    # ─── STAGE 2: THE VOICE ─────────────────────────────────
    voice_stage_msg = (
        "Deep writing in your voice..."
        if voice_mode == VoiceMode.deep_voice
        else "Writing in your voice..."
    )
    yield sse_event("stage", stage="voice", message=voice_stage_msg)

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
            voice_mode=voice_mode,
            voice_model=voice_model,
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

    # ─── SLOP VALIDATION (feature-gated) ────────────────────
    if is_enabled("slop_validator"):
        try:
            slop_result = slop_validator.validate(full_output, {"anti_slop": anti_slop or {}})
            yield sse_event("slop_score", data=slop_result)
        except Exception as e:
            logger.warning("[GENERATION] Slop validation failed (non-fatal): %s", e)

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

    # ─── POST-GENERATION: EXTRACTION LOOP (feature-gated) ───
    if project and is_enabled("extraction_loop"):
        existing_bible = project.get("story_bible") or {}
        try:
            yield sse_event(
                "stage", stage="extraction", message="Analyzing your scene..."
            )
            final_prose = polished_output or full_output
            suggestions = await extract_story_facts(
                prose=final_prose,
                existing_bible=existing_bible,
                genre=project.get("genre"),
            )

            # Filter out knowledge/timeline results if those features are disabled
            if not is_enabled("knowledge_state"):
                suggestions.knowledge_events = []
            if not is_enabled("timeline_engine"):
                suggestions.timeline_events = []
                suggestions.state_changes = []
                suggestions.contradiction_warnings = []

            has_suggestions = (
                suggestions.new_characters
                or suggestions.new_locations
                or suggestions.character_updates
                or suggestions.new_world_rules
                or suggestions.plot_beats
                or suggestions.knowledge_events
                or suggestions.timeline_events
                or suggestions.state_changes
                or suggestions.contradiction_warnings
            )

            if has_suggestions:
                yield sse_event(
                    "bible_suggestions",
                    suggestions=suggestions.model_dump(),
                )
        except Exception as e:
            # Extraction failure should never block the generation
            logger.error("[EXTRACTION] Extraction loop failed: %s", e)

    yield sse_event("done", metadata={
        "word_count": word_count,
        "generation_id": generation_id,
        "voice_mode": voice_mode.value,
        "voice_model": voice_model or "deepseek-v3",
    })


# --- Refine Pipeline (Voice-only with feedback) ---

async def run_refine_pipeline(
    user_id: str,
    generation_id: str,
    feedback: str,
    voice_instruction: str,
    anti_slop: dict | None,
    include_polish: bool,
    voice_mode: VoiceMode = VoiceMode.default,
    voice_model: str | None = None,
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
            voice_mode=voice_mode,
        )
    except Exception as e:
        logger.error("[GENERATION] Failed to store refine generation: %s", e)
        yield sse_event("error", content="Failed to save generation.")
        return

    # Voice stage with feedback
    refine_msg = (
        "Deep rewriting with your feedback..."
        if voice_mode == VoiceMode.deep_voice
        else "Rewriting with your feedback..."
    )
    yield sse_event("stage", stage="voice", message=refine_msg)

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
            voice_mode=voice_mode,
            voice_model=voice_model,
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
        "voice_mode": voice_mode.value,
        "voice_model": voice_model or "deepseek-v3",
    })


# --- Beat-Driven Generation ---


def find_beat_in_outline(
    outline: dict, beat_id: str
) -> tuple[dict | None, dict | None, dict | None]:
    """Locate a beat in the outline. Returns (beat, chapter, part) or (None, None, None)."""
    for part in outline.get("parts", []):
        for chapter in part.get("chapters", []):
            for beat in chapter.get("beats", []):
                if beat.get("beat_id") == beat_id:
                    return beat, chapter, part
    return None, None, None


def _find_previous_beat_id(outline: dict, current_beat_id: str) -> str | None:
    """Find the beat_id of the beat immediately before the current one."""
    all_beats: list[str] = []
    for part in outline.get("parts", []):
        for chapter in part.get("chapters", []):
            for beat in chapter.get("beats", []):
                all_beats.append(beat.get("beat_id", ""))

    try:
        idx = all_beats.index(current_beat_id)
        return all_beats[idx - 1] if idx > 0 else None
    except ValueError:
        return None


async def get_previous_beat_output(
    outline: dict, beat_id: str, project_id: str
) -> str | None:
    """Load the voice_output from the previous beat's generation for continuity."""
    prev_beat_id = _find_previous_beat_id(outline, beat_id)
    if not prev_beat_id:
        return None

    prev_beat, _, _ = find_beat_in_outline(outline, prev_beat_id)
    if not prev_beat or not prev_beat.get("generation_id"):
        return None

    supabase = get_supabase_client()
    result = (
        supabase.table("generations")
        .select("voice_output")
        .eq("id", prev_beat["generation_id"])
        .execute()
    )
    if result.data and result.data[0].get("voice_output"):
        return result.data[0]["voice_output"]
    return None


def build_beat_prompt(
    beat: dict,
    chapter: dict,
    part: dict,
    previous_output: str | None,
    additional_context: str | None,
) -> str:
    """Build a generation prompt from outline beat context."""
    parts = []

    parts.append(f"Write Chapter {chapter.get('chapter_number', '?')}: {chapter.get('title', '')}")
    parts.append(f"\nBEAT: {beat.get('template_beat', '')}")
    parts.append(f"WHAT HAPPENS: {beat.get('description', '')}")

    if beat.get("pov_character"):
        parts.append(f"POV: {beat['pov_character']}")

    if beat.get("estimated_words"):
        parts.append(f"TARGET LENGTH: ~{beat['estimated_words']} words")

    if previous_output:
        last_500 = " ".join(previous_output.split()[-500:])
        parts.append(f"\nPREVIOUS SCENE ENDED WITH:\n...{last_500}")
        parts.append("\nContinue seamlessly from where the previous scene left off.")

    if additional_context:
        parts.append(f"\nAUTHOR'S NOTES: {additional_context}")

    return "\n".join(parts)


async def update_beat_status(
    project_id: str,
    beat_id: str,
    new_status: str,
    generation_id: str | None = None,
    clear_generation_id: bool = False,
) -> None:
    """Update a beat's status and generation_id in the project's outline.

    If clear_generation_id=True, sets generation_id to None (used on rollback).
    """
    supabase = get_supabase_client()
    result = (
        supabase.table("projects")
        .select("story_bible")
        .eq("id", project_id)
        .execute()
    )
    if not result.data:
        return

    story_bible = result.data[0].get("story_bible") or {}
    outline = story_bible.get("outline")
    if not outline:
        return

    for part_data in outline.get("parts", []):
        for chapter_data in part_data.get("chapters", []):
            for beat_data in chapter_data.get("beats", []):
                if beat_data.get("beat_id") == beat_id:
                    beat_data["status"] = new_status
                    if generation_id:
                        beat_data["generation_id"] = generation_id
                    elif clear_generation_id:
                        beat_data["generation_id"] = None

    story_bible["outline"] = outline
    supabase.table("projects").update(
        {"story_bible": story_bible}
    ).eq("id", project_id).execute()

    logger.info(
        "[GENERATION] Updated beat %s status to %s (gen: %s)",
        beat_id, new_status, generation_id,
    )


async def run_beat_generation(
    user_id: str,
    project: dict,
    voice_instruction: str,
    anti_slop: dict | None,
    beat_id: str,
    include_polish: bool = False,
    additional_context: str | None = None,
    voice_mode: VoiceMode = VoiceMode.default,
    voice_model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Generate prose for a specific beat from the outline."""
    outline = (project.get("story_bible") or {}).get("outline")
    if not outline or not outline.get("locked"):
        yield sse_event("error", content="Outline must be locked before generating.")
        return

    beat, chapter, part = find_beat_in_outline(outline, beat_id)
    if not beat:
        yield sse_event("error", content=f"Beat {beat_id} not found in outline.")
        return

    # Mark beat as generating
    await update_beat_status(project["id"], beat_id, "generating")

    # Get previous beat's output for continuity
    previous_output = await get_previous_beat_output(outline, beat_id, project["id"])

    # Build prompt from the beat
    prompt = build_beat_prompt(beat, chapter, part, previous_output, additional_context)

    # Preserve the previous successful scene link on failed regenerates.
    prior_generation_id = beat.get("generation_id")

    # Run through the main pipeline, watching for terminal events
    generation_id = None
    pipeline_succeeded = False

    try:
        async for event in run_generation_pipeline(
            user_id=user_id,
            prompt=prompt,
            voice_instruction=voice_instruction,
            anti_slop=anti_slop,
            project=project,
            include_polish=include_polish,
            previous_output=previous_output,
            voice_mode=voice_mode,
            voice_model=voice_model,
        ):
            # Watch for terminal events to determine success/failure
            if '"type": "done"' in event:
                try:
                    import json as _json
                    data = _json.loads(event.replace("data: ", "").strip())
                    generation_id = data.get("metadata", {}).get("generation_id")
                    pipeline_succeeded = True
                except Exception:
                    pass
            elif '"type": "error"' in event:
                pipeline_succeeded = False
            yield event

        # Update beat status based on outcome
        if pipeline_succeeded and generation_id:
            await update_beat_status(project["id"], beat_id, "generated", generation_id)
        elif not pipeline_succeeded:
            # Pipeline reported an error via SSE — roll back so user can retry.
            # Only clear generation_id if there was no prior successful scene.
            logger.warning("[GENERATION] Pipeline error event for beat %s, rolling back", beat_id)
            rollback_status = "generated" if prior_generation_id else "pending"
            await update_beat_status(
                project["id"], beat_id, rollback_status,
                clear_generation_id=prior_generation_id is None,
            )
    except Exception as e:
        logger.error("[GENERATION] Beat generation exception for %s: %s", beat_id, e)
        rollback_status = "generated" if prior_generation_id else "pending"
        await update_beat_status(
            project["id"], beat_id, rollback_status,
            clear_generation_id=prior_generation_id is None,
        )
        raise
