"""Pydantic models for the Projects System.

Defines request/response schemas for project CRUD and scene management.
All UUID fields use str (not uuid.UUID) for Supabase compatibility.
"""

from datetime import datetime

from pydantic import BaseModel, field_validator


# --- Project CRUD ---


class CreateProjectRequest(BaseModel):
    """Create a new writing project."""

    title: str
    genre: str | None = None
    distribution_format: str | None = "kindle_ebook"
    voice_profile_id: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project title cannot be empty.")
        if len(v) > 200:
            raise ValueError("Project title must be 200 characters or less.")
        return v


class UpdateProjectRequest(BaseModel):
    """Update an existing project. All fields optional — only sends changed fields."""

    title: str | None = None
    genre: str | None = None
    distribution_format: str | None = None
    voice_profile_id: str | None = None
    story_bible: dict | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Project title cannot be empty.")
            if len(v) > 200:
                raise ValueError("Project title must be 200 characters or less.")
        return v


class ProjectListItem(BaseModel):
    """Summary of a project for dashboard listing."""

    id: str
    title: str
    genre: str | None = None
    distribution_format: str | None = None
    voice_profile_id: str | None = None
    voice_profile_name: str | None = None
    scene_count: int = 0
    total_words: int = 0
    last_generated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ProjectListResponse(BaseModel):
    """Response wrapper for project listings."""

    projects: list[ProjectListItem]


class ProjectDetailResponse(BaseModel):
    """Full project detail (for workspace load)."""

    id: str
    title: str
    genre: str | None = None
    distribution_format: str | None = None
    voice_profile_id: str | None = None
    voice_profile_name: str | None = None
    story_bible: dict = {}
    scene_count: int = 0
    total_words: int = 0
    created_at: datetime
    updated_at: datetime


# --- Scene Management ---


class SceneListItem(BaseModel):
    """Scene summary for sidebar listing (no full text)."""

    id: str
    user_prompt: str
    scene_label: str | None = None
    word_count: int | None = None
    is_pinned: bool = False
    scene_order: int | None = None
    has_polish: bool = False
    created_at: datetime


class SceneListResponse(BaseModel):
    """Response wrapper for scene listings."""

    scenes: list[SceneListItem]


class SceneDetailResponse(BaseModel):
    """Full scene content (loaded when user clicks a scene)."""

    id: str
    user_prompt: str
    scene_label: str | None = None
    voice_output: str = ""
    polish_output: str | None = None
    brain_output: str | None = None
    word_count: int | None = None
    is_pinned: bool = False
    scene_order: int | None = None
    created_at: datetime


class UpdateSceneRequest(BaseModel):
    """Update scene metadata or content. All fields optional."""

    scene_label: str | None = None
    scene_order: int | None = None
    is_pinned: bool | None = None
    voice_output: str | None = None


class ReorderRequest(BaseModel):
    """Bulk reorder scenes by providing ordered scene IDs."""

    scene_ids: list[str]
