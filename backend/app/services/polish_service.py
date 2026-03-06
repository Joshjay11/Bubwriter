"""Polish service — Claude Sonnet line-editing pass (Stage 3, Author tier only).

Uses the Anthropic API directly for Claude Sonnet. Not streamed — returns
the full polished text as a replacement for the Voice output.
"""

import logging

import httpx

from app.config import settings
from app.prompts.polish_prompt import POLISH_SYSTEM, POLISH_USER

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
POLISH_MODEL = "claude-sonnet-4-5-20250929"


async def run_polish(
    prose: str,
    voice_instruction: str,
    anti_slop_rules: str,
) -> str:
    """Run Claude Sonnet polish pass. Returns full edited text.

    This is a non-streaming call — the polished text replaces the
    Voice output in the frontend.
    """
    system_prompt = POLISH_SYSTEM.format(
        voice_instruction=voice_instruction,
        anti_slop_rules=anti_slop_rules,
    )
    user_prompt = POLISH_USER.format(prose=prose)

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": settings.anthropic_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": POLISH_MODEL,
                "max_tokens": 4000,
                "temperature": 0.3,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt},
                ],
            },
        )

        if response.status_code != 200:
            error_detail = response.text
            logger.error(
                "[GENERATION] Polish API error %d: %s",
                response.status_code,
                error_detail,
            )
            raise RuntimeError(
                f"Polish API returned {response.status_code}: {error_detail}"
            )

        data = response.json()
        polished = data["content"][0]["text"]
        logger.info(
            "[GENERATION] Polish complete (%d chars)",
            len(polished),
        )
        return polished
