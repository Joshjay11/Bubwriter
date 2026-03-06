"""Voice service — DeepSeek V3 streaming prose generation (Stage 2).

Streams prose tokens from V3 via the OpenAI-compatible API.
Uses the writer's voice_instruction and anti-slop constraints
to generate prose that sounds like the user wrote it.
"""

import logging
from collections.abc import AsyncGenerator

import openai

from app.config import settings
from app.models.generation_schemas import SceneSkeleton
from app.prompts.voice_prompt import VOICE_SYSTEM, VOICE_USER

logger = logging.getLogger(__name__)

DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
VOICE_MODEL = "deepseek-ai/DeepSeek-V3-0324"


def _get_clients() -> list[openai.AsyncOpenAI]:
    """Return ordered list of LLM clients for V3."""
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


def format_skeleton_for_voice(skeleton: SceneSkeleton | str) -> str:
    """Convert JSON skeleton to readable format for the Voice model."""
    if isinstance(skeleton, str):
        return skeleton  # fallback: raw text

    lines = [f"SCENE: {skeleton.scene_title}"]
    lines.append(f"OPENING: {skeleton.opening_hook}")
    lines.append(f"TENSION ARC: {skeleton.tension_arc or 'Not specified'}")
    lines.append("")

    for beat in skeleton.beats:
        lines.append(f"BEAT {beat.beat_number}:")
        lines.append(f"  Action: {beat.action}")
        lines.append(f"  Emotional tone: {beat.emotional_tone}")
        if beat.pov_character:
            lines.append(f"  POV: {beat.pov_character}")
        if beat.setting_detail:
            lines.append(f"  Setting: {beat.setting_detail}")
        if beat.dialogue_hint:
            lines.append(f"  Dialogue goal: {beat.dialogue_hint}")
        if beat.internal_state:
            lines.append(f"  Internal: {beat.internal_state}")
        lines.append("")

    lines.append(f"CLOSING IMAGE: {skeleton.closing_image}")
    if skeleton.style_notes:
        lines.append(f"STYLE NOTES: {skeleton.style_notes}")

    return "\n".join(lines)


async def stream_voice(
    skeleton: str,
    voice_instruction: str,
    anti_slop_rules: str,
    story_context: str,
    target_word_count: int = 2000,
    additional_instructions: str = "",
) -> AsyncGenerator[str, None]:
    """Stream prose tokens from DeepSeek V3.

    Yields individual text chunks as they arrive from the model.
    """
    system_prompt = VOICE_SYSTEM.format(
        voice_instruction=voice_instruction,
        anti_slop_rules=anti_slop_rules,
        target_word_count=target_word_count,
    )

    user_prompt = VOICE_USER.format(
        readable_skeleton=skeleton,
        story_context=story_context or "No story context provided.",
    )

    if additional_instructions:
        user_prompt += f"\n\n## ADDITIONAL INSTRUCTIONS\n{additional_instructions}"

    clients = _get_clients()
    last_error: Exception | None = None

    for client in clients:
        try:
            stream = await client.chat.completions.create(
                model=VOICE_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=1.3,
                top_p=0.95,
                frequency_penalty=0.3,
                presence_penalty=0.2,
                max_tokens=4000,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            return

        except Exception as e:
            logger.warning(
                "[GENERATION] Voice stream failed with %s: %s",
                type(e).__name__,
                e,
            )
            last_error = e
            continue

    raise last_error or RuntimeError("No LLM providers available for Voice")
