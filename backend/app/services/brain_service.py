"""Brain service — Claude Sonnet scene skeleton generation (Stage 1, v2).

Uses the Anthropic API directly (same pattern as polish_service.py).
v2 change: Migrated from DeepSeek R1 via DeepInfra to Claude Sonnet via
Anthropic. Claude handles system prompts properly, producing more
reliable structured JSON output for scene skeletons.
"""

import json
import logging
import re

import httpx

from app.config import settings
from app.prompts.brain_prompt import BRAIN_SYSTEM, BRAIN_USER

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
BRAIN_MODEL = "claude-sonnet-4-5-20250929"


def _clean_json_response(raw: str) -> str:
    """Strip markdown fencing and preamble from LLM JSON output."""
    cleaned = raw.strip()
    # Remove ```json ... ``` wrapping
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


async def run_brain(
    prompt: str,
    story_context: str = "",
    continuation_context: str = "",
    genre_guardrails: str = "",
    retry: bool = False,
) -> str:
    """Run Claude Sonnet to generate a scene skeleton as JSON.

    Returns the raw JSON string (validated by caller).
    On retry, adds tighter constraints to the user prompt.
    """
    user_prompt = BRAIN_USER.format(
        user_prompt=prompt,
        story_context=story_context or "No story context available.",
        genre_guardrails=genre_guardrails or "No genre or format constraints.",
        continuation_context=continuation_context or "This is a standalone scene.",
    )

    if retry:
        user_prompt += (
            "\n\nIMPORTANT: Your previous attempt had formatting issues. "
            "Return ONLY a valid JSON object. No text before or after. "
            "Ensure all required fields are present: scene_title, opening_hook, "
            "beats (array with at least 4 items), closing_image."
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
                    "model": BRAIN_MODEL,
                    "max_tokens": 4000,
                    "temperature": 0.4,
                    "system": BRAIN_SYSTEM,
                    "messages": [
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )

            if response.status_code != 200:
                error_detail = response.text
                logger.error(
                    "[GENERATION] Brain API error %d: %s",
                    response.status_code,
                    error_detail,
                )
                raise RuntimeError(
                    f"Brain API returned {response.status_code}: {error_detail}"
                )

            data = response.json()
            content = data["content"][0]["text"]

            cleaned = _clean_json_response(content)

            # Validate it's parseable JSON before returning
            json.loads(cleaned)

            logger.info("[GENERATION] Brain skeleton generated (%d chars)", len(cleaned))
            return cleaned

    except httpx.HTTPError as e:
        logger.error("[GENERATION] Brain HTTP error: %s", e)
        raise RuntimeError(f"Brain API request failed: {e}") from e
