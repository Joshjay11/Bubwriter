"""Voice service — multi-model streaming prose generation (Stage 2).

Dispatches to the correct Voice model based on voice_profile.voice_model.
Supports DeepSeek V3 (DeepInfra), Mistral Small Creative (OpenRouter),
and Llama 3.3 70B (DeepInfra) with per-provider fallback.

v3: Added voice model routing. Each profile stores its preferred model.
    OpenRouter promoted to first-class provider for Mistral.
    Legacy voice_mode (V3 vs R1) still supported via stream_voice().
"""

import asyncio
import logging
from collections.abc import AsyncGenerator

import httpx
import openai

from app.config import settings
from app.models.generation_schemas import SceneSkeleton, VoiceMode
from app.prompts.voice_prompt import VOICE_SYSTEM, VOICE_USER

logger = logging.getLogger(__name__)


# --- Provider Configuration ---

PROVIDER_CONFIG = {
    "deepinfra": {
        "base_url": "https://api.deepinfra.com/v1/openai",
        "api_key_attr": "deepinfra_api_key",
        "health_endpoint": "https://api.deepinfra.com/v1/openai/models",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_attr": "openrouter_api_key",
        "health_endpoint": "https://openrouter.ai/api/v1/models",
        "extra_headers": {
            "HTTP-Referer": "https://bubwriter.com",
            "X-Title": "BUB Writer",
        },
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "api_key_attr": "fireworks_api_key",
    },
}


# --- Voice Model Registry ---

VOICE_MODEL_MAP: dict[str, dict] = {
    "deepseek-v3": {
        "model_id": "deepseek-ai/DeepSeek-V3-0324",
        "provider": "deepinfra",
        "fallback_model": "deepseek/deepseek-chat",
        "fallback_provider": "openrouter",
    },
    "mistral-small-creative": {
        "model_id": "mistralai/mistral-small-creative",
        "provider": "openrouter",
        "fallback_model": "deepseek-ai/DeepSeek-V3-0324",
        "fallback_provider": "deepinfra",
    },
    "llama-70b": {
        "model_id": "meta-llama/Llama-3.3-70B-Instruct",
        "provider": "deepinfra",
        "fallback_model": "meta-llama/llama-3.3-70b-instruct",
        "fallback_provider": "openrouter",
    },
}

# Per-model generation parameters — tuned from benchmark results
VOICE_PARAMS: dict[str, dict] = {
    "deepseek-v3": {
        "temperature": 1.3,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
        "top_p": 0.95,
        "max_tokens": 4000,
    },
    "mistral-small-creative": {
        "temperature": 1.2,
        "frequency_penalty": 0.25,
        "presence_penalty": 0.1,
        "top_p": 0.95,
        "max_tokens": 4000,
    },
    "llama-70b": {
        "temperature": 0.9,
        "frequency_penalty": 0.2,
        "presence_penalty": 0.1,
        "top_p": 0.95,
        "max_tokens": 4000,
    },
}

# Legacy voice_mode presets (V3 default vs R1 deep_voice)
VOICE_MODE_MODELS = {
    VoiceMode.default: {
        "model": "deepseek-ai/DeepSeek-V3-0324",
        "temperature": 1.3,
        "top_p": 0.95,
        "frequency_penalty": 0.3,
        "presence_penalty": 0.2,
        "max_tokens": 4000,
    },
    VoiceMode.deep_voice: {
        "model": "deepseek-ai/DeepSeek-R1",
        "temperature": 0.9,
        "top_p": 0.95,
        "frequency_penalty": 0.4,
        "presence_penalty": 0.3,
        "max_tokens": 8000,
    },
}


# --- Provider Client Factory ---

def _get_provider_client(provider: str) -> openai.AsyncOpenAI:
    """Create an OpenAI-compatible client for the given provider."""
    config = PROVIDER_CONFIG[provider]
    api_key = getattr(settings, config["api_key_attr"], "")
    if not api_key:
        raise ProviderUnavailableError(f"No API key configured for {provider}")

    kwargs: dict = {
        "api_key": api_key,
        "base_url": config["base_url"],
    }
    if "extra_headers" in config:
        kwargs["default_headers"] = config["extra_headers"]

    return openai.AsyncOpenAI(**kwargs)


def _get_deepinfra_fireworks_clients() -> list[openai.AsyncOpenAI]:
    """Return ordered list of DeepInfra + Fireworks clients (legacy fallback chain)."""
    clients = [
        openai.AsyncOpenAI(
            api_key=settings.deepinfra_api_key,
            base_url=PROVIDER_CONFIG["deepinfra"]["base_url"],
        ),
    ]
    if settings.fireworks_api_key:
        clients.append(
            openai.AsyncOpenAI(
                api_key=settings.fireworks_api_key,
                base_url=PROVIDER_CONFIG["fireworks"]["base_url"],
            ),
        )
    return clients


# --- Exceptions ---

class ProviderUnavailableError(Exception):
    """Raised when a provider is down or unreachable."""


class RateLimitError(Exception):
    """Raised on 429 responses."""


# --- Health Check ---

async def check_provider_health(provider: str) -> bool:
    """Lightweight health check — GET models endpoint, expect 200."""
    config = PROVIDER_CONFIG.get(provider)
    if not config or "health_endpoint" not in config:
        return True

    api_key = getattr(settings, config["api_key_attr"], "")
    if not api_key:
        return False

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                config["health_endpoint"],
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return response.status_code == 200
    except Exception:
        return False


# --- Skeleton Formatter ---

def format_skeleton_for_voice(skeleton: SceneSkeleton | str) -> str:
    """Convert JSON skeleton to readable format for the Voice model."""
    if isinstance(skeleton, str):
        return skeleton

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


# --- Streaming from Provider ---

async def _stream_from_provider(
    provider: str,
    model_id: str,
    messages: list[dict[str, str]],
    params: dict,
    max_retries: int = 3,
) -> AsyncGenerator[str, None]:
    """Stream tokens from a provider with retry on 429."""
    client = _get_provider_client(provider)

    for attempt in range(max_retries):
        try:
            stream = await client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=params["temperature"],
                top_p=params.get("top_p", 0.95),
                frequency_penalty=params.get("frequency_penalty", 0),
                presence_penalty=params.get("presence_penalty", 0),
                max_tokens=params.get("max_tokens", 4000),
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content
            return
        except openai.RateLimitError:
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "[GENERATION] Rate limited by %s, retry %d in %ds",
                    provider, attempt + 1, wait,
                )
                await asyncio.sleep(wait)
            else:
                raise ProviderUnavailableError(
                    f"Rate limited by {provider} after {max_retries} retries"
                )
        except (openai.APIConnectionError, openai.APITimeoutError, openai.InternalServerError) as e:
            logger.warning("[GENERATION] Provider %s unavailable: %s", provider, e)
            raise ProviderUnavailableError(f"{provider} unavailable: {e}")


# --- Voice Model Dispatcher (NEW) ---

async def call_voice_model(
    voice_model: str,
    messages: list[dict[str, str]],
) -> AsyncGenerator[str, None]:
    """Dispatch to the correct Voice model with fallback.

    Reads model config from VOICE_MODEL_MAP, uses VOICE_PARAMS for
    generation parameters. Falls back to fallback_model/provider if
    the primary provider is unavailable.
    """
    if voice_model not in VOICE_MODEL_MAP:
        logger.warning(
            "[GENERATION] Unknown voice_model '%s', defaulting to deepseek-v3",
            voice_model,
        )
        voice_model = "deepseek-v3"

    model_cfg = VOICE_MODEL_MAP[voice_model]
    params = VOICE_PARAMS[voice_model]

    logger.info(
        "[GENERATION] Voice model dispatch: %s via %s",
        model_cfg["model_id"], model_cfg["provider"],
    )

    try:
        async for token in _stream_from_provider(
            provider=model_cfg["provider"],
            model_id=model_cfg["model_id"],
            messages=messages,
            params=params,
        ):
            yield token
        return
    except ProviderUnavailableError as e:
        logger.warning("[GENERATION] Primary provider failed: %s", e)

        if model_cfg.get("fallback_model") and model_cfg.get("fallback_provider"):
            logger.info(
                "[GENERATION] Falling back to %s via %s",
                model_cfg["fallback_model"], model_cfg["fallback_provider"],
            )
            async for token in _stream_from_provider(
                provider=model_cfg["fallback_provider"],
                model_id=model_cfg["fallback_model"],
                messages=messages,
                params=params,
            ):
                yield token
        else:
            raise


# --- Voice Message Builder ---

def build_voice_messages(
    skeleton: str,
    voice_instruction: str,
    anti_slop_rules: str,
    story_context: str,
    target_word_count: int = 2000,
    additional_instructions: str = "",
) -> list[dict[str, str]]:
    """Build the system + user messages for any Voice model."""
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

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# --- Legacy stream_voice (still used by refine pipeline) ---

async def stream_voice(
    skeleton: str,
    voice_instruction: str,
    anti_slop_rules: str,
    story_context: str,
    target_word_count: int = 2000,
    additional_instructions: str = "",
    voice_mode: VoiceMode = VoiceMode.default,
    voice_model: str | None = None,
) -> AsyncGenerator[str, None]:
    """Stream prose tokens using voice model routing or legacy voice_mode.

    If voice_model is provided (from profile), uses the new dispatch path.
    Otherwise falls back to legacy VoiceMode behavior (V3/R1 via DeepInfra).
    """
    # New path: route via voice_model from profile
    if voice_model and voice_model in VOICE_MODEL_MAP:
        messages = build_voice_messages(
            skeleton=skeleton,
            voice_instruction=voice_instruction,
            anti_slop_rules=anti_slop_rules,
            story_context=story_context,
            target_word_count=target_word_count,
            additional_instructions=additional_instructions,
        )
        async for token in call_voice_model(voice_model, messages):
            yield token
        return

    # Legacy path: voice_mode (V3 default / R1 deep_voice) via DeepInfra+Fireworks
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

    preset = VOICE_MODE_MODELS[voice_mode]
    model_name = preset["model"]

    clients = _get_deepinfra_fireworks_clients()
    last_error: Exception | None = None

    logger.info("[GENERATION] Voice mode: %s, model: %s", voice_mode.value, model_name)

    for client in clients:
        try:
            stream = await client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=preset["temperature"],
                top_p=preset["top_p"],
                frequency_penalty=preset["frequency_penalty"],
                presence_penalty=preset["presence_penalty"],
                max_tokens=preset["max_tokens"],
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta
                # R1 (deep_voice) emits reasoning_content tokens — skip them
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    continue
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
