"""Post-generation extraction loop.

Analyzes generated prose against the existing Story Bible and returns
structured suggestions for new entities. Does NOT write to database —
returns suggestions only. The user approves or dismisses each suggestion.
"""

import json
import logging
import re

import httpx
from pydantic import BaseModel, Field

from app.config import settings
from app.prompts.extraction_prompt import EXTRACTION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
EXTRACTION_MODEL = "claude-sonnet-4-5-20250929"


# ── Suggestion Models ────────────────────────────────────


class CharacterSuggestion(BaseModel):
    name: str
    description: str = ""
    role: str = "minor"  # protagonist, supporting, minor, mentioned
    first_appearance: str = ""


class LocationSuggestion(BaseModel):
    name: str
    description: str = ""
    sensory_details: dict = Field(default_factory=dict)
    first_appearance: str = ""


class CharacterUpdate(BaseModel):
    character_name: str
    character_id: str | None = None
    update_type: str  # "new_knowledge", "status_change", "relationship", "knowledge_boundary"
    detail: str


class WorldRuleSuggestion(BaseModel):
    category: str  # "magic", "technology", "politics", "social", etc.
    rule: str
    exceptions: list[str] = Field(default_factory=list)
    implications: str = ""


class PlotBeatSuggestion(BaseModel):
    beat: str
    characters_involved: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)


class KnowledgeEvent(BaseModel):
    type: str  # "secret_established", "knowledge_gained", "pov_leak_warning"
    summary: str
    character_names: list[str] = Field(default_factory=list)
    witnesses: list[str] = Field(default_factory=list)
    non_witnesses: list[str] = Field(default_factory=list)
    method: str | None = None  # how they learned it
    issue: str | None = None  # for POV leak warnings


class ExtractionResult(BaseModel):
    """All fields Optional — LLM won't always find every category."""

    new_characters: list[CharacterSuggestion] = Field(default_factory=list)
    new_locations: list[LocationSuggestion] = Field(default_factory=list)
    character_updates: list[CharacterUpdate] = Field(default_factory=list)
    new_world_rules: list[WorldRuleSuggestion] = Field(default_factory=list)
    plot_beats: list[PlotBeatSuggestion] = Field(default_factory=list)
    knowledge_events: list[KnowledgeEvent] = Field(default_factory=list)


# ── Extraction Logic ─────────────────────────────────────


def _format_bible_for_extraction(bible: dict) -> str:
    """Format existing bible as context for the extraction prompt."""
    parts: list[str] = []
    if bible.get("characters"):
        chars = [
            f"- {c.get('name', 'unnamed')} ({c.get('role', 'unknown')})"
            for c in bible["characters"]
        ]
        parts.append("Known characters:\n" + "\n".join(chars))
    if bible.get("locations"):
        locs = [f"- {l.get('name', 'unnamed')}" for l in bible["locations"]]
        parts.append("Known locations:\n" + "\n".join(locs))
    if bible.get("world_rules"):
        rules = [f"- {r.get('rule', '')}" for r in bible["world_rules"]]
        parts.append("Established world rules:\n" + "\n".join(rules))
    if bible.get("story_secrets"):
        secrets = []
        for s in bible["story_secrets"]:
            who_knows = ", ".join(s.get("characters_who_know", []))
            who_doesnt = ", ".join(s.get("characters_who_dont_know", []))
            secrets.append(
                f"- SECRET: {s.get('summary', '')}\n"
                f"  Known by: {who_knows or 'no one yet'}\n"
                f"  Unknown to: {who_doesnt or 'n/a'}"
            )
        parts.append("Active secrets:\n" + "\n".join(secrets))
    return "\n\n".join(parts) if parts else "(Empty — no entries yet)"


async def extract_story_facts(
    prose: str,
    existing_bible: dict,
    genre: str | None = None,
) -> ExtractionResult:
    """Analyze generated prose against existing Story Bible.

    Returns suggestions for new entities and updates.
    Does NOT write to database — returns suggestions only.
    Uses Claude Sonnet (same API key as Brain + Polish).
    """
    bible_summary = _format_bible_for_extraction(existing_bible)

    existing_characters = [
        c.get("name", "").lower() for c in existing_bible.get("characters", [])
    ]
    existing_locations = [
        loc.get("name", "").lower() for loc in existing_bible.get("locations", [])
    ]

    user_content = (
        f"Analyze this scene for new narrative elements to track.\n\n"
        f"EXISTING STORY BIBLE:\n{bible_summary}\n\n"
        f"GENERATED SCENE:\n{prose}\n\n"
    )
    if genre:
        user_content += f"GENRE: {genre}\n\n"
    user_content += (
        "Return a JSON object with your findings. "
        "If no new elements are found in a category, return an empty array for that category."
    )

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": EXTRACTION_MODEL,
                    "max_tokens": 2000,
                    "temperature": 0.3,
                    "system": EXTRACTION_SYSTEM_PROMPT,
                    "messages": [
                        {"role": "user", "content": user_content},
                    ],
                },
            )

            if response.status_code != 200:
                logger.error(
                    "[EXTRACTION] API error %d: %s",
                    response.status_code,
                    response.text,
                )
                return ExtractionResult()

            data = response.json()
            raw_text = data["content"][0]["text"]

    except httpx.HTTPError as e:
        logger.error("[EXTRACTION] HTTP error: %s", e)
        return ExtractionResult()

    # Parse response — handle LLM JSON inconsistency
    result = _parse_extraction_response(raw_text)

    # Filter out entities that already exist in the bible
    result.new_characters = [
        c for c in result.new_characters
        if c.name.lower() not in existing_characters
    ]
    result.new_locations = [
        loc for loc in result.new_locations
        if loc.name.lower() not in existing_locations
    ]

    logger.info(
        "[EXTRACTION] Found %d characters, %d locations, %d updates, %d rules, %d beats, %d knowledge events",
        len(result.new_characters),
        len(result.new_locations),
        len(result.character_updates),
        len(result.new_world_rules),
        len(result.plot_beats),
        len(result.knowledge_events),
    )
    return result


def _parse_extraction_response(raw_text: str) -> ExtractionResult:
    """Parse LLM response into ExtractionResult, handling JSON inconsistencies."""
    # Try direct parse first
    try:
        return ExtractionResult.model_validate_json(raw_text)
    except Exception:
        pass

    # Try to extract JSON from markdown code blocks
    json_match = re.search(r"```json?\s*(.*?)\s*```", raw_text, re.DOTALL)
    if json_match:
        try:
            return ExtractionResult.model_validate(json.loads(json_match.group(1)))
        except Exception:
            pass

    # Try to find any JSON object in the response
    try:
        # Find first { and last }
        start = raw_text.index("{")
        end = raw_text.rindex("}") + 1
        return ExtractionResult.model_validate(json.loads(raw_text[start:end]))
    except Exception:
        pass

    # Graceful degradation — return empty result
    logger.warning("[EXTRACTION] Failed to parse response, returning empty result")
    return ExtractionResult()
