"""Outline router — Story Architect outline compilation, editing, and locking.

Endpoints:
  POST   /projects/{project_id}/outline/compile  — Compile brainstorm into outline
  PATCH  /projects/{project_id}/outline           — Update outline (edit beats, etc.)
  POST   /projects/{project_id}/outline/lock      — Lock outline for generation
  GET    /projects/{project_id}/outline            — Get current outline
  GET    /outline/templates                        — List all structure templates
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.core.features import is_enabled
from app.services.outline_service import compile_outline
from app.services.structure_templates import get_all_templates
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["outline"])


# --- Request/Response Models ---


class CompileOutlineRequest(BaseModel):
    """Request to compile an outline from brainstorm decisions."""
    brainstorm_decisions: list[str] | None = None
    structure_override: str | None = None


class UpdateOutlineRequest(BaseModel):
    """Partial outline update — replaces the outline in story_bible."""
    outline: dict


# --- Helpers ---


def _load_project(project_id: str, user_id: str) -> dict:
    """Load project and verify ownership."""
    supabase = get_supabase_client()
    result = (
        supabase.table("projects")
        .select("*")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found.",
        )
    return result.data[0]


def _save_outline(project_id: str, user_id: str, outline: dict) -> None:
    """Save outline into the project's story_bible JSONB."""
    supabase = get_supabase_client()

    # Load current story_bible to merge (don't overwrite other sections)
    result = (
        supabase.table("projects")
        .select("story_bible")
        .eq("id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    story_bible = (result.data[0].get("story_bible") or {}) if result.data else {}
    story_bible["outline"] = outline

    supabase.table("projects").update({
        "story_bible": story_bible,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", project_id).eq("user_id", user_id).execute()


# --- Endpoints ---


@router.get("/outline/templates")
async def list_templates() -> dict:
    """List all available structure templates. Public endpoint."""
    return {"templates": get_all_templates()}


@router.post("/projects/{project_id}/outline/compile")
async def compile_project_outline(
    project_id: str,
    compile_request: CompileOutlineRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Compile brainstorm output into a structured outline.

    Returns the suggested outline without saving. The user reviews
    and edits before locking.
    """
    if not is_enabled("story_outline"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Story outline feature is not enabled.",
        )

    project = _load_project(project_id, user_id)

    try:
        outline = await compile_outline(
            project=project,
            brainstorm_decisions=compile_request.brainstorm_decisions,
            structure_override=compile_request.structure_override,
        )
    except RuntimeError as e:
        logger.error("[OUTLINE] Compilation failed for project %s: %s", project_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Outline compilation failed: {e}",
        )

    # Return without saving — user reviews and edits before saving via PATCH
    logger.info("[OUTLINE] Compiled outline for project %s (not saved yet)", project_id)
    return {"outline": outline}


@router.get("/projects/{project_id}/outline")
async def get_outline(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Get the current outline for a project."""
    project = _load_project(project_id, user_id)
    outline = (project.get("story_bible") or {}).get("outline")

    if not outline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No outline exists for this project. Compile one first.",
        )

    return {"outline": outline}


@router.patch("/projects/{project_id}/outline")
async def update_outline(
    project_id: str,
    update_request: UpdateOutlineRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Update the outline (edit beats, reorder chapters, change titles).

    Replaces the outline section in story_bible with the provided data.
    Cannot update a locked outline.
    """
    project = _load_project(project_id, user_id)
    existing_outline = (project.get("story_bible") or {}).get("outline")

    if existing_outline and existing_outline.get("locked"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Outline is locked. Unlock it before making changes.",
        )

    _save_outline(project_id, user_id, update_request.outline)

    logger.info("[OUTLINE] Updated outline for project %s", project_id)
    return {"outline": update_request.outline}


@router.post("/projects/{project_id}/outline/lock")
async def lock_outline(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict:
    """Lock the outline for generation. Cannot lock if any beat has empty description."""
    project = _load_project(project_id, user_id)
    outline = (project.get("story_bible") or {}).get("outline")

    if not outline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No outline exists to lock.",
        )

    if outline.get("locked"):
        return {"outline": outline, "message": "Outline is already locked."}

    # Validate: no empty beat descriptions
    for part in outline.get("parts", []):
        for chapter in part.get("chapters", []):
            for beat in chapter.get("beats", []):
                if not beat.get("description", "").strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Beat '{beat.get('template_beat', 'Unknown')}' in Chapter {chapter.get('chapter_number', '?')} has no description. Fill in all beats before locking.",
                    )

    outline["locked"] = True
    outline["locked_at"] = datetime.now(timezone.utc).isoformat()

    _save_outline(project_id, user_id, outline)

    logger.info("[OUTLINE] Locked outline for project %s", project_id)
    return {"outline": outline}
