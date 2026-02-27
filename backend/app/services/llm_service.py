"""LLM service — DeepSeek V3 via DeepInfra with Fireworks fallback.

Supports both non-streaming (analyze, finalize) and streaming (interview)
calls using the OpenAI-compatible API format.
"""

import logging
from collections.abc import AsyncIterator

import openai

from app.config import settings

logger = logging.getLogger(__name__)

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

DEFAULT_MODEL = "deepseek-ai/DeepSeek-V3"


def _get_clients() -> list[openai.AsyncOpenAI]:
    """Return ordered list of LLM clients: DeepInfra primary, Fireworks fallback."""
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


async def generate(
    system_prompt: str,
    user_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4000,
) -> str:
    """Non-streaming LLM call. Tries DeepInfra, falls back to Fireworks.

    Used for sample analysis and profile compilation where we need
    the full response before processing.
    """
    clients = _get_clients()
    last_error: Exception | None = None

    for client in clients:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty content")
            return content
        except Exception as e:
            logger.warning("LLM generate failed with %s: %s", type(e).__name__, e)
            last_error = e
            continue

    raise last_error or RuntimeError("No LLM providers available")


async def generate_stream(
    system_prompt: str,
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.8,
) -> AsyncIterator[str]:
    """Streaming LLM call. Yields text chunks as they arrive.

    Used for the interview endpoint where we stream the AI's
    response to the frontend via SSE.
    """
    clients = _get_clients()
    last_error: Exception | None = None

    for client in clients:
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                temperature=temperature,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            return
        except Exception as e:
            logger.warning("LLM stream failed with %s: %s", type(e).__name__, e)
            last_error = e
            continue

    raise last_error or RuntimeError("No LLM providers available")
