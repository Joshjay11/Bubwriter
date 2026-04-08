"""Story DNA service — synthesize finalized interview into profile + concepts.

Wraps the LLM call against story_dna_concepts prompt and parses the JSON
response into a profile dict and concepts list.
"""

import json
import logging

from app.prompts.story_dna_concepts import (
    STORY_DNA_CONCEPTS_SYSTEM,
    STORY_DNA_CONCEPTS_USER,
)
from app.services import llm_service

logger = logging.getLogger(__name__)


def _build_transcript(turns: list[dict[str, str]]) -> str:
    lines = []
    for msg in turns:
        role = "Interviewer" if msg["role"] == "assistant" else "User"
        lines.append(f"{role}: {msg['content']}")
    return "\n\n".join(lines)


def _strip_fences(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines)
    return cleaned


async def synthesize_dna(turns: list[dict[str, str]]) -> tuple[dict, list[dict]]:
    """Run the concept-generator prompt against finalized turns.

    Returns (story_dna_profile, concepts). Raises on LLM or JSON failure.
    Retries once on JSON parse failure.
    """
    transcript = _build_transcript(turns)
    user_prompt = STORY_DNA_CONCEPTS_USER.format(transcript=transcript)

    last_raw = ""
    for attempt in range(2):
        raw = await llm_service.generate(
            system_prompt=STORY_DNA_CONCEPTS_SYSTEM,
            user_prompt=user_prompt,
            temperature=0.8,
            max_tokens=4000,
        )
        last_raw = raw
        try:
            payload = json.loads(_strip_fences(raw))
            profile = payload.get("story_dna_profile") or {}
            concepts = payload.get("concepts") or []
            if not profile or not concepts:
                raise ValueError("Missing story_dna_profile or concepts in payload")
            return profile, concepts
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning("[STORY_DNA] synth attempt %d failed: %s", attempt + 1, e)
            continue

    logger.error("[STORY_DNA] synthesis failed after retry. Last raw: %s", last_raw[:500])
    raise RuntimeError("Story DNA synthesis failed")
