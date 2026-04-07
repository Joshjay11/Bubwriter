"""Outline service — compiles brainstorm output into a structured outline.

Uses Claude Sonnet to map brainstorm decisions onto a structure template,
producing a chapter-by-chapter outline with beats.
"""

import json
import logging
import uuid

import httpx

from app.config import settings
from app.prompts.outline_compiler import OUTLINE_COMPILER_SYSTEM, OUTLINE_COMPILER_USER
from app.services.structure_templates import (
    STRUCTURE_TEMPLATES,
    get_recommended_structure,
)

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
OUTLINE_MODEL = "claude-sonnet-4-5-20250929"


def format_template_beats(beats: list[dict]) -> str:
    """Format template beats into readable text for the LLM."""
    lines = []
    for b in beats:
        lines.append(f"  {b['position']}. {b['name']} ({b['pct']}%): {b['description']}")
    return "\n".join(lines)


def format_bible_summary(bible: dict) -> str:
    """Format existing story bible into a readable summary."""
    parts = []
    for section in ("characters", "locations", "world_rules", "plot_beats"):
        items = bible.get(section, [])
        if items:
            parts.append(f"\n{section.upper()}:")
            for item in items:
                if isinstance(item, dict):
                    name = item.get("name", item.get("title", "Unknown"))
                    desc = item.get("description", item.get("summary", ""))
                    parts.append(f"  - {name}: {desc}")
                else:
                    parts.append(f"  - {item}")
    return "\n".join(parts) if parts else ""


async def compile_outline(
    project: dict,
    brainstorm_decisions: list[str] | None = None,
    structure_override: str | None = None,
) -> dict:
    """Compile brainstorm output into a structured outline.

    1. Pick structure template (genre-based recommendation or user override)
    2. Send template beats + brainstorm decisions to Claude Sonnet
    3. Claude populates each beat with story-specific content
    4. Return structured outline for user review
    """
    genre = project.get("genre")
    distribution_format = project.get("distribution_format")

    # Pick structure
    template_key = structure_override or get_recommended_structure(genre, distribution_format)
    if template_key not in STRUCTURE_TEMPLATES:
        template_key = "save_the_cat_15"
    template = STRUCTURE_TEMPLATES[template_key]

    # Build contexts
    brainstorm_context = ""
    if brainstorm_decisions:
        decisions = "\n".join(f"- {d}" for d in brainstorm_decisions)
        brainstorm_context = f"\nSTORY DECISIONS FROM BRAINSTORMING:\n{decisions}"

    bible_context = ""
    bible = project.get("story_bible", {})
    bible_summary = format_bible_summary(bible)
    if bible_summary:
        bible_context = f"\nEXISTING STORY BIBLE:\n{bible_summary}"

    user_prompt = OUTLINE_COMPILER_USER.format(
        title=project.get("title", "Untitled"),
        genre=genre or "Not specified — infer from the story decisions",
        distribution_format=distribution_format or "kindle_ebook",
        structure_name=template["name"],
        beat_count=len(template["beats"]),
        beat_template=format_template_beats(template["beats"]),
        brainstorm_context=brainstorm_context,
        bible_context=bible_context,
    )

    # Call Claude Sonnet
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": OUTLINE_MODEL,
                "max_tokens": 8000,
                "temperature": 0.5,
                "system": OUTLINE_COMPILER_SYSTEM,
                "messages": [
                    {"role": "user", "content": user_prompt},
                ],
            },
        )

        if response.status_code != 200:
            error_detail = response.text
            logger.error(
                "[OUTLINE] Compilation API error %d: %s",
                response.status_code,
                error_detail,
            )
            raise RuntimeError(
                f"Outline compilation failed ({response.status_code}): {error_detail}"
            )

        data = response.json()
        raw_text = data["content"][0]["text"]

    # Parse JSON from response (handle markdown code blocks)
    outline_json = _extract_json(raw_text)

    # Post-process: add beat_ids, statuses, and template metadata
    outline = _post_process_outline(outline_json, template_key, template["name"])

    logger.info(
        "[OUTLINE] Compiled outline: %d parts, %d chapters",
        len(outline.get("parts", [])),
        sum(len(p.get("chapters", [])) for p in outline.get("parts", [])),
    )

    return outline


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Try to find JSON in code blocks first
    import re
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block:
        text = code_block.group(1)

    # Try to find the outermost JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("[OUTLINE] Failed to parse outline JSON: %s", e)
        raise RuntimeError("Failed to parse outline from LLM response") from e


def _post_process_outline(
    outline_json: dict,
    template_key: str,
    template_name: str,
) -> dict:
    """Add metadata, beat_ids, and status fields to the raw LLM outline."""
    beat_counter = 0

    for part in outline_json.get("parts", []):
        for chapter in part.get("chapters", []):
            for beat in chapter.get("beats", []):
                beat_counter += 1
                if not beat.get("beat_id"):
                    beat["beat_id"] = f"beat_{beat_counter:03d}"
                beat.setdefault("status", "pending")
                beat.setdefault("generation_id", None)
                beat.setdefault("estimated_words", 2500)

    outline = {
        "structure_template": template_key,
        "structure_name": template_name,
        "total_chapters": sum(
            len(p.get("chapters", []))
            for p in outline_json.get("parts", [])
        ),
        "parts": outline_json.get("parts", []),
        "locked": False,
        "locked_at": None,
    }

    if outline_json.get("genre_recommendation"):
        outline["genre_recommendation"] = outline_json["genre_recommendation"]

    return outline
