"""Pydantic request/response models for the BUB Writer API.

All API endpoints use these schemas for consistent validation
and serialization. Expand as features are implemented.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    service: str


# --- Voice Discovery ---

class AnalyzeRequest(BaseModel):
    writing_sample: str
    sample_context: str = ""

    @field_validator("writing_sample")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        """Enforce 500-10000 word limits on writing samples."""
        word_count = len(v.split())
        if word_count < 500:
            raise ValueError(
                "Please provide at least 500 words for accurate analysis."
            )
        if word_count > 10000:
            raise ValueError(
                "Please keep the sample under 10,000 words."
            )
        return v


class StyleMarkers(BaseModel):
    vocabulary_tier: str
    avg_sentence_length: str
    sentence_variety: str
    pacing_style: str
    emotional_register: str
    sensory_preference: str
    dialogue_style: str
    pov_tendency: str
    tense_preference: str
    dark_humor_quotient: str
    notable_patterns: list[str]
    comparable_authors: list[str]


class AnalyzeResponse(BaseModel):
    session_id: str
    style_markers: StyleMarkers


class InterviewRequest(BaseModel):
    session_id: str
    user_message: str = ""


class FinalizeRequest(BaseModel):
    session_id: str
    profile_name: str

    @field_validator("profile_name")
    @classmethod
    def validate_profile_name(cls, v: str) -> str:
        """Ensure profile name is non-empty and within length limits."""
        v = v.strip()
        if not v:
            raise ValueError("Profile name cannot be empty.")
        if len(v) > 100:
            raise ValueError("Profile name must be 100 characters or less.")
        return v


class CognitiveStyle(BaseModel):
    processing_mode: str
    story_entry_point: str
    revision_pattern: str
    plotter_pantser: str


class LiteraryDNA(BaseModel):
    vocabulary_tier: str
    sentence_rhythm: str
    pacing_style: str
    emotional_register: str
    sensory_mode: str
    dialogue_approach: str
    pov_preference: str
    tense_preference: str
    humor_style: str
    darkness_calibration: str
    cognitive_style: CognitiveStyle
    notable_patterns: list[str]
    comparable_authors: list[str]


class Influences(BaseModel):
    rhythm_from: list[str]
    structure_from: list[str]
    tone_from: list[str]
    anti_influences: list[str]


class AntiSlop(BaseModel):
    personal_banned_words: list[str]
    personal_banned_patterns: list[str]
    cringe_triggers: list[str]
    genre_constraints: list[str]


class FinalizeResponse(BaseModel):
    profile_id: str
    profile_name: str
    literary_dna: LiteraryDNA
    influences: Influences
    anti_slop: AntiSlop
    voice_instruction: str
    voice_summary: str


# --- Voice Profiles ---

class VoiceProfileBase(BaseModel):
    profile_name: str
    literary_dna: dict
    influences: dict = {}
    anti_slop: dict = {}
    voice_instruction: str | None = None


class VoiceProfileCreate(VoiceProfileBase):
    pass


class VoiceProfileResponse(VoiceProfileBase):
    id: UUID
    user_id: UUID
    created_at: datetime
    updated_at: datetime


class VoiceProfileListItem(BaseModel):
    id: str
    profile_name: str
    voice_summary: str | None
    created_at: datetime
    updated_at: datetime


class VoiceProfileListResponse(BaseModel):
    profiles: list[VoiceProfileListItem]


# --- Projects ---

class ProjectBase(BaseModel):
    title: str
    genre: str | None = None
    story_bible: dict = {}


class ProjectCreate(ProjectBase):
    voice_profile_id: UUID | None = None


class ProjectResponse(ProjectBase):
    id: UUID
    user_id: UUID
    voice_profile_id: UUID | None
    created_at: datetime
    updated_at: datetime


# --- Generations ---

class GenerationRequest(BaseModel):
    project_id: UUID
    user_prompt: str


class GenerationResponse(BaseModel):
    id: UUID
    project_id: UUID
    user_prompt: str
    voice_output: str
    polish_output: str | None
    word_count: int | None
    created_at: datetime


# --- Subscriptions ---

class SubscriptionResponse(BaseModel):
    id: UUID
    user_id: UUID
    tier: str
    status: str
    current_period_end: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Placeholder ---

class PlaceholderResponse(BaseModel):
    status: str
    router: str
