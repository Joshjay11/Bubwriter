"""Pydantic models for the Generation Pipeline (Brain -> Voice -> Polish).

Defines scene skeletons, pipeline request/response schemas, and SSE event types.
All LLM-facing models use Optional fields with defaults — LLMs don't reliably
produce every field every time.
"""

from enum import Enum

from pydantic import BaseModel


# --- Voice Mode ---

class VoiceMode(str, Enum):
    """Controls which model powers the Voice (prose generation) stage.

    default: DeepSeek V3 — fast, high-temperature creative writing.
    deep_voice: DeepSeek R1 — slower, more deliberate and nuanced prose.
    """
    default = "default"
    deep_voice = "deep_voice"


# --- Scene Skeleton (Brain output) ---

class Beat(BaseModel):
    """A single narrative beat in the scene skeleton."""
    beat_number: int
    action: str
    emotional_tone: str
    pov_character: str | None = None
    setting_detail: str | None = None
    dialogue_hint: str | None = None
    internal_state: str | None = None


class SceneSkeleton(BaseModel):
    """Scene structure produced by the Brain (DeepSeek R1)."""
    scene_title: str
    opening_hook: str
    beats: list[Beat]
    closing_image: str
    tension_arc: str | None = None
    themes: list[str] = []
    target_word_count: int = 2000
    style_notes: str | None = None


# --- Pipeline Request Models ---

class GenerateRequest(BaseModel):
    """Primary generation endpoint request."""
    project_id: str | None = None
    voice_profile_id: str
    prompt: str
    context: str | None = None
    include_polish: bool = False
    previous_scene_id: str | None = None
    voice_mode: VoiceMode = VoiceMode.default


class ContinueRequest(BaseModel):
    """Continue from a previous generation."""
    project_id: str | None = None
    voice_profile_id: str
    generation_id: str
    prompt: str | None = None
    include_polish: bool = False
    voice_mode: VoiceMode = VoiceMode.default


class RefineRequest(BaseModel):
    """Re-run Voice stage with user feedback, reusing the Brain skeleton."""
    generation_id: str
    feedback: str
    voice_profile_id: str
    include_polish: bool = False
    voice_mode: VoiceMode = VoiceMode.default


class BeatGenerateRequest(BaseModel):
    """Generate prose from a specific outline beat."""
    project_id: str
    voice_profile_id: str
    beat_id: str
    additional_context: str | None = None
    include_polish: bool = False
    voice_mode: VoiceMode = VoiceMode.default
