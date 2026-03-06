"""Brain service — DeepSeek R1 scene skeleton generation (Stage 1).

Uses DeepInfra (primary) / Fireworks (fallback) for the R1 model.
R1 performs better without system prompts — all instructions in user prompt.
The `reasoning_content` field is stored for debug but NEVER fed back.
"""

import json
import logging
import re

import openai

from app.config import settings
from app.prompts.brain_prompt import BRAIN_SYSTEM, BRAIN_USER

logger = logging.getLogger(__name__)

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
BRAIN_MODEL = "deepseek-ai/DeepSeek-R1"


def _get_clients() -> list[openai.AsyncOpenAI]:
    """Return ordered list of LLM clients for R1."""
    clients = [
        openai.AsyncOpenAI(
            api_key=settings.deepinfra_api_key,
            base_url=DEEPINFRA_BASE_URL,
        ),
    ]
    if settings.fireworks_api_key:
        clients.append(
            openai.AsyncOpenAI(
                api_key=settings.fireworks_api_key,
                base_url=FIREWORKS_BASE_URL,
            ),
        )
    return clients


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
    retry: bool = False,
) -> str:
    """Run DeepSeek R1 to generate a scene skeleton as JSON.

    Returns the raw JSON string (validated by caller).
    On retry, adds tighter constraints to the prompt.
    """
    user_prompt = BRAIN_USER.format(
        user_prompt=prompt,
        story_context=story_context or "No story context available.",
        continuation_context=continuation_context or "This is a standalone scene.",
    )

    if retry:
        user_prompt += (
            "\n\nIMPORTANT: Your previous attempt had formatting issues. "
            "Return ONLY a valid JSON object. No text before or after. "
            "Ensure all required fields are present: scene_title, opening_hook, "
            "beats (array with at least 4 items), closing_image."
        )

    clients = _get_clients()
    last_error: Exception | None = None

    messages: list[dict[str, str]] = []
    if BRAIN_SYSTEM:
        messages.append({"role": "system", "content": BRAIN_SYSTEM})
    messages.append({"role": "user", "content": user_prompt})

    for client in clients:
        try:
            response = await client.chat.completions.create(
                model=BRAIN_MODEL,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.6,
                top_p=0.95,
                max_tokens=4000,
                frequency_penalty=0.4,
                presence_penalty=0.2,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("R1 returned empty content")

            cleaned = _clean_json_response(content)

            # Validate it's parseable JSON before returning
            json.loads(cleaned)

            logger.info("[GENERATION] Brain skeleton generated (%d chars)", len(cleaned))
            return cleaned

        except Exception as e:
            logger.warning(
                "[GENERATION] Brain failed with %s: %s", type(e).__name__, e
            )
            last_error = e
            continue

    raise last_error or RuntimeError("No LLM providers available for Brain")
