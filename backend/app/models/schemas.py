"""Pydantic request/response models for the BUB Writer API.

All API endpoints use these schemas for consistent validation
and serialization. Expand as features are implemented.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


# --- Health ---

class HealthResponse(BaseModel):
    status: str
    service: str


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
