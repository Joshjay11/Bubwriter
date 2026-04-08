"""Background voice extraction from conversational turns.

Reads how a user writes (not what they wrote about) and produces a
voice_signal dict that can refine an existing voice profile. Used by:

- Story DNA Analyzer finalize (Phase 2/3): seeds the starter voice
  profile when the user later migrates the session.
- Brainstorm respond endpoint (this phase): refines the project's
  linked voice profile every N turns, in the background, without
  blocking the SSE stream.

This service ONLY refines profiles where profile_source IN
('dna_analyzer', 'brainstorm'). It will never touch a profile that
came from the full Voice Discovery interview.
"""

import json
import logging

from app.services import llm_service
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


REFINABLE_SOURCES = {"dna_analyzer", "brainstorm"}


_VOICE_EXTRACTION_SYSTEM = """You are a passive voice analyzer. You are given a \
short series of messages a writer wrote during a brainstorming conversation. \
Your job is to extract a snapshot of HOW they write — not what they wrote \
about. You output STRICT JSON only.

Look at the writer's own messages and infer:
- vocabulary_tier: plain | conversational | literary | ornate
- sentence_rhythm: clipped | balanced | flowing | sprawling
- sensory_bias: visual | auditory | tactile | interior | mixed
- emotional_temperature: cool | measured | warm | intense
- humor_presence: none | dry | warm | absurd | dark
- notes: 1-2 sentences naming anything else distinctive about HOW they wrote \
(metaphor habits, hedging, idiom, etc.)

OUTPUT
Return JSON exactly in this shape:
{
  "voice_signal": {
    "vocabulary_tier": "...",
    "sentence_rhythm": "...",
    "sensory_bias": "...",
    "emotional_temperature": "...",
    "humor_presence": "...",
    "notes": "..."
  }
}

RULES
- Choose enum values exactly as listed.
- Never invent observations. If a dimension is unclear from the text, pick \
the closest enum value and say so briefly in notes.
- Output JSON only. No code fences, no commentary.
"""


def _strip_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    return cleaned


def _build_user_turns_blob(turns: list[dict[str, str]]) -> str:
    lines = []
    for i, msg in enumerate(turns, start=1):
        if msg.get("role") != "user":
            continue
        content = (msg.get("content") or "").strip()
        if content:
            lines.append(f"[Message {i}]\n{content}")
    return "\n\n".join(lines)


async def extract_voice_signal(turns: list[dict[str, str]]) -> dict | None:
    """Run the extractor against a list of conversation turns.

    Returns a voice_signal dict, or None on failure (extraction is
    best-effort and must never break the calling endpoint).
    """
    user_blob = _build_user_turns_blob(turns)
    if not user_blob or len(user_blob.split()) < 30:
        # Not enough material to extract from yet
        return None

    try:
        raw = await llm_service.generate(
            system_prompt=_VOICE_EXTRACTION_SYSTEM,
            user_prompt=f"Writer's messages:\n\n{user_blob}",
            temperature=0.4,
            max_tokens=600,
        )
        payload = json.loads(_strip_fences(raw))
        signal = payload.get("voice_signal")
        if isinstance(signal, dict) and signal:
            return signal
    except Exception as e:
        logger.warning("[VOICE_EXTRACT] extraction failed: %s", e)
    return None


def _merge_signal_into_literary_dna(
    existing: dict | None, signal: dict
) -> dict:
    """Merge new voice_signal into the literary_dna JSON shape we store.

    Always overwrites the dimensions the extractor produced — these are
    the latest read on the writer's voice. Preserves other fields the
    profile may have (e.g. notable_patterns from earlier passes).
    """
    merged = dict(existing or {})
    if signal.get("vocabulary_tier"):
        merged["vocabulary_tier"] = signal["vocabulary_tier"]
    if signal.get("sentence_rhythm"):
        merged["sentence_rhythm"] = signal["sentence_rhythm"]
    if signal.get("sensory_bias"):
        merged["sensory_mode"] = signal["sensory_bias"]
    if signal.get("emotional_temperature"):
        merged["emotional_register"] = signal["emotional_temperature"]
    if signal.get("humor_presence"):
        merged["humor_style"] = signal["humor_presence"]
    if signal.get("notes"):
        notes = merged.get("notable_patterns") or []
        # Keep history compact — last 5 notes max
        notes = (notes + [signal["notes"]])[-5:]
        merged["notable_patterns"] = notes
    return merged


def _build_voice_instruction_from_dna(literary_dna: dict) -> str:
    """Render an updated starter voice instruction from a refined literary_dna."""
    vocab = literary_dna.get("vocabulary_tier") or "conversational"
    rhythm = literary_dna.get("sentence_rhythm") or "balanced"
    sensory = literary_dna.get("sensory_mode") or "mixed"
    temp = literary_dna.get("emotional_register") or "measured"
    humor = literary_dna.get("humor_style") or "none"
    notes = literary_dna.get("notable_patterns") or []

    parts = [
        "You are the writer. This voice is being refined as the writer keeps working with BUB Writer.",
        "",
        "VOICE SIGNATURE",
        f"- Vocabulary: {vocab}",
        f"- Sentence rhythm: {rhythm}",
        f"- Sensory bias: {sensory} detail",
        f"- Emotional temperature: {temp}",
        f"- Humor: {humor}",
    ]
    if notes:
        parts.append("- Distinctive habits:")
        for n in notes:
            parts.append(f"  • {n}")
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


async def refine_project_voice_from_brainstorm(
    project_id: str,
    user_id: str,
    conversation_history: list[dict[str, str]],
) -> None:
    """Best-effort: refine a project's linked voice profile from brainstorm turns.

    Skips silently if:
    - The project has no linked voice profile
    - The voice profile's source is not in REFINABLE_SOURCES
    - There isn't enough user material to extract from
    - Anything in the LLM or DB call path raises

    Promotes a 'dna_analyzer' source profile to 'brainstorm' on first
    successful refinement.
    """
    try:
        supabase = get_supabase_client()

        proj_result = (
            supabase.table("projects")
            .select("voice_profile_id")
            .eq("id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not proj_result.data:
            return
        voice_profile_id = proj_result.data[0].get("voice_profile_id")
        if not voice_profile_id:
            return

        vp_result = (
            supabase.table("voice_profiles")
            .select("id, literary_dna, profile_source")
            .eq("id", voice_profile_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not vp_result.data:
            return
        vp = vp_result.data[0]
        source = vp.get("profile_source") or "interview"
        if source not in REFINABLE_SOURCES:
            logger.info(
                "[VOICE_EXTRACT] skipping refinement — profile %s is source=%s",
                voice_profile_id,
                source,
            )
            return

        signal = await extract_voice_signal(conversation_history)
        if not signal:
            return

        merged = _merge_signal_into_literary_dna(vp.get("literary_dna"), signal)
        new_instruction = _build_voice_instruction_from_dna(merged)
        new_source = "brainstorm"  # promote dna_analyzer → brainstorm on first refine

        supabase.table("voice_profiles").update(
            {
                "literary_dna": merged,
                "voice_instruction": new_instruction,
                "profile_source": new_source,
            }
        ).eq("id", voice_profile_id).eq("user_id", user_id).execute()

        logger.info(
            "[VOICE_EXTRACT] refined voice profile %s (source %s → %s)",
            voice_profile_id,
            source,
            new_source,
        )
    except Exception as e:
        logger.warning("[VOICE_EXTRACT] refine_project_voice failed: %s", e)
