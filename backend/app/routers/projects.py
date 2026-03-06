"""Projects router — CRUD for writing projects and scene management.

Endpoints:
  POST   /projects                                — Create project
  GET    /projects                                — List user's projects
  GET    /projects/{project_id}                   — Get project detail
  PATCH  /projects/{project_id}                   — Update project
  DELETE /projects/{project_id}                   — Delete project + scenes
  GET    /projects/{project_id}/scenes            — List scenes (sidebar)
  GET    /projects/{project_id}/scenes/{gen_id}   — Get full scene
  PATCH  /projects/{project_id}/scenes/{gen_id}   — Update scene
  DELETE /projects/{project_id}/scenes/{gen_id}   — Delete scene
  POST   /projects/{project_id}/scenes/reorder    — Bulk reorder
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.project_schemas import (
    CreateProjectRequest,
    ProjectDetailResponse,
    ProjectListItem,
    ProjectListResponse,
    ReorderRequest,
    SceneDetailResponse,
    SceneListItem,
    SceneListResponse,
    UpdateProjectRequest,
    UpdateSceneRequest,
)
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# --- Helpers ---


def _verify_project_ownership(project_id: str, user_id: str) -> dict:
    """Load project and verify it belongs to user. Raises 404 if not found."""
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


def _get_voice_profile_name(voice_profile_id: str | None) -> str | None:
    """Fetch voice profile name by ID. Returns None if not found."""
    if not voice_profile_id:
        return None
    supabase = get_supabase_client()
    result = (
        supabase.table("voice_profiles")
        .select("profile_name")
        .eq("id", voice_profile_id)
        .execute()
    )
    if result.data:
        return result.data[0].get("profile_name")
    return None


def _get_project_stats(user_id: str) -> dict[str, dict]:
    """Fetch scene count, total words, and last generated time per project.

    Uses the get_project_stats database function to avoid N+1 queries.
    Falls back to client-side computation if the function doesn't exist.
    """
    supabase = get_supabase_client()
    try:
        result = supabase.rpc(
            "get_project_stats", {"p_user_id": user_id}
        ).execute()
        return {
            str(s["project_id"]): s for s in (result.data or [])
        }
    except Exception:
        # Fallback: fetch raw generation data and compute stats in Python
        logger.warning(
            "[PROJECTS] get_project_stats RPC not available, computing client-side"
        )
        result = (
            supabase.table("generations")
            .select("project_id, word_count, created_at")
            .eq("user_id", user_id)
            .not_.is_("project_id", "null")
            .execute()
        )
        stats: dict[str, dict] = {}
        for row in result.data or []:
            pid = str(row["project_id"])
            if pid not in stats:
                stats[pid] = {
                    "project_id": pid,
                    "scene_count": 0,
                    "total_words": 0,
                    "last_generated_at": None,
                }
            stats[pid]["scene_count"] += 1
            stats[pid]["total_words"] += row.get("word_count") or 0
            row_time = row.get("created_at")
            if row_time and (
                stats[pid]["last_generated_at"] is None
                or row_time > stats[pid]["last_generated_at"]
            ):
                stats[pid]["last_generated_at"] = row_time
        return stats


def _build_project_detail(
    project: dict,
    voice_profile_name: str | None = None,
    stats: dict | None = None,
) -> ProjectDetailResponse:
    """Build a ProjectDetailResponse from a raw Supabase row."""
    return ProjectDetailResponse(
        id=project["id"],
        title=project["title"],
        genre=project.get("genre"),
        voice_profile_id=project.get("voice_profile_id"),
        voice_profile_name=voice_profile_name,
        story_bible=project.get("story_bible") or {},
        scene_count=stats.get("scene_count", 0) if stats else 0,
        total_words=stats.get("total_words", 0) if stats else 0,
        created_at=project["created_at"],
        updated_at=project["updated_at"],
    )


# --- Project CRUD ---


@router.post("", response_model=ProjectDetailResponse)
async def create_project(
    create_request: CreateProjectRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> ProjectDetailResponse:
    """Create a new writing project."""
    supabase = get_supabase_client()

    # Validate voice profile belongs to user if provided
    voice_profile_name = None
    if create_request.voice_profile_id:
        vp_result = (
            supabase.table("voice_profiles")
            .select("id, profile_name")
            .eq("id", create_request.voice_profile_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not vp_result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Voice profile not found or doesn't belong to you.",
            )
        voice_profile_name = vp_result.data[0].get("profile_name")

    insert_data = {
        "user_id": user_id,
        "title": create_request.title,
        "genre": create_request.genre,
        "voice_profile_id": create_request.voice_profile_id,
        "story_bible": {},
    }

    try:
        result = supabase.table("projects").insert(insert_data).execute()
    except Exception as e:
        logger.error("[PROJECTS] Failed to create project: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project.",
        )

    project = result.data[0]
    logger.info("[PROJECTS] Created project %s for user %s", project["id"], user_id)

    return _build_project_detail(project, voice_profile_name=voice_profile_name)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user_id: Annotated[str, Depends(get_current_user)],
) -> ProjectListResponse:
    """List all projects for the authenticated user with stats."""
    supabase = get_supabase_client()

    result = (
        supabase.table("projects")
        .select("*")
        .eq("user_id", user_id)
        .order("updated_at", desc=True)
        .execute()
    )

    if not result.data:
        return ProjectListResponse(projects=[])

    # Fetch stats and voice profile names
    stats_map = _get_project_stats(user_id)

    # Collect unique voice_profile_ids to batch-fetch names
    vp_ids = {
        p["voice_profile_id"]
        for p in result.data
        if p.get("voice_profile_id")
    }
    vp_names: dict[str, str] = {}
    if vp_ids:
        vp_result = (
            supabase.table("voice_profiles")
            .select("id, profile_name")
            .in_("id", list(vp_ids))
            .execute()
        )
        vp_names = {vp["id"]: vp["profile_name"] for vp in (vp_result.data or [])}

    projects = []
    for p in result.data:
        pid = p["id"]
        s = stats_map.get(pid, {})
        projects.append(
            ProjectListItem(
                id=pid,
                title=p["title"],
                genre=p.get("genre"),
                voice_profile_id=p.get("voice_profile_id"),
                voice_profile_name=vp_names.get(p.get("voice_profile_id", ""), None),
                scene_count=s.get("scene_count", 0),
                total_words=s.get("total_words", 0),
                last_generated_at=s.get("last_generated_at"),
                created_at=p["created_at"],
                updated_at=p["updated_at"],
            )
        )

    return ProjectListResponse(projects=projects)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> ProjectDetailResponse:
    """Get a single project with stats."""
    project = _verify_project_ownership(project_id, user_id)
    voice_profile_name = _get_voice_profile_name(project.get("voice_profile_id"))

    stats_map = _get_project_stats(user_id)
    stats = stats_map.get(project_id, {})

    return _build_project_detail(project, voice_profile_name, stats)


@router.patch("/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: str,
    update_request: UpdateProjectRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> ProjectDetailResponse:
    """Update project fields. Only sends changed fields."""
    project = _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    update_data: dict = {}
    if update_request.title is not None:
        update_data["title"] = update_request.title
    if update_request.genre is not None:
        update_data["genre"] = update_request.genre
    if update_request.story_bible is not None:
        update_data["story_bible"] = update_request.story_bible
    if update_request.voice_profile_id is not None:
        # Validate voice profile belongs to user
        vp_result = (
            supabase.table("voice_profiles")
            .select("id")
            .eq("id", update_request.voice_profile_id)
            .eq("user_id", user_id)
            .execute()
        )
        if not vp_result.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Voice profile not found or doesn't belong to you.",
            )
        update_data["voice_profile_id"] = update_request.voice_profile_id

    if not update_data:
        # Nothing to update — return current state
        voice_profile_name = _get_voice_profile_name(project.get("voice_profile_id"))
        stats_map = _get_project_stats(user_id)
        return _build_project_detail(
            project, voice_profile_name, stats_map.get(project_id, {})
        )

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            supabase.table("projects")
            .update(update_data)
            .eq("id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        logger.error("[PROJECTS] Failed to update project %s: %s", project_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update project.",
        )

    updated = result.data[0]
    voice_profile_name = _get_voice_profile_name(updated.get("voice_profile_id"))
    stats_map = _get_project_stats(user_id)

    logger.info("[PROJECTS] Updated project %s", project_id)
    return _build_project_detail(
        updated, voice_profile_name, stats_map.get(project_id, {})
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict[str, bool]:
    """Delete a project and all its generations."""
    _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    try:
        # Delete generations first (explicit cascade)
        supabase.table("generations").delete().eq(
            "project_id", project_id
        ).eq("user_id", user_id).execute()

        # Delete the project
        supabase.table("projects").delete().eq("id", project_id).eq(
            "user_id", user_id
        ).execute()
    except Exception as e:
        logger.error("[PROJECTS] Failed to delete project %s: %s", project_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete project.",
        )

    logger.info("[PROJECTS] Deleted project %s and its generations", project_id)
    return {"deleted": True}


# --- Scene Management ---


@router.get("/{project_id}/scenes", response_model=SceneListResponse)
async def list_scenes(
    project_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SceneListResponse:
    """List all scenes (generations) for a project. No full text returned."""
    _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    result = (
        supabase.table("generations")
        .select(
            "id, user_prompt, scene_label, word_count, is_pinned, "
            "scene_order, polish_output, created_at"
        )
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .order("is_pinned", desc=True)
        .order("scene_order", desc=False)
        .order("created_at", desc=False)
        .execute()
    )

    scenes = [
        SceneListItem(
            id=row["id"],
            user_prompt=row.get("user_prompt", ""),
            scene_label=row.get("scene_label"),
            word_count=row.get("word_count"),
            is_pinned=row.get("is_pinned", False),
            scene_order=row.get("scene_order"),
            has_polish=row.get("polish_output") is not None,
            created_at=row["created_at"],
        )
        for row in (result.data or [])
    ]

    return SceneListResponse(scenes=scenes)


@router.get("/{project_id}/scenes/{gen_id}", response_model=SceneDetailResponse)
async def get_scene(
    project_id: str,
    gen_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SceneDetailResponse:
    """Get full scene content including voice_output."""
    _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    result = (
        supabase.table("generations")
        .select("*")
        .eq("id", gen_id)
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found.",
        )

    row = result.data[0]
    return SceneDetailResponse(
        id=row["id"],
        user_prompt=row.get("user_prompt", ""),
        scene_label=row.get("scene_label"),
        voice_output=row.get("voice_output", ""),
        polish_output=row.get("polish_output"),
        brain_output=row.get("brain_output"),
        word_count=row.get("word_count"),
        is_pinned=row.get("is_pinned", False),
        scene_order=row.get("scene_order"),
        created_at=row["created_at"],
    )


@router.patch("/{project_id}/scenes/{gen_id}", response_model=SceneDetailResponse)
async def update_scene(
    project_id: str,
    gen_id: str,
    update_request: UpdateSceneRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> SceneDetailResponse:
    """Update scene metadata or content."""
    _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    # Verify scene exists and belongs to user
    existing = (
        supabase.table("generations")
        .select("id")
        .eq("id", gen_id)
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found.",
        )

    update_data: dict = {}
    if update_request.scene_label is not None:
        update_data["scene_label"] = update_request.scene_label
    if update_request.scene_order is not None:
        update_data["scene_order"] = update_request.scene_order
    if update_request.is_pinned is not None:
        update_data["is_pinned"] = update_request.is_pinned
    if update_request.voice_output is not None:
        update_data["voice_output"] = update_request.voice_output
        update_data["word_count"] = len(update_request.voice_output.split())

    if not update_data:
        # Nothing to update — return current state
        return await get_scene(project_id, gen_id, user_id)

    try:
        result = (
            supabase.table("generations")
            .update(update_data)
            .eq("id", gen_id)
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        logger.error("[PROJECTS] Failed to update scene %s: %s", gen_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update scene.",
        )

    row = result.data[0]
    return SceneDetailResponse(
        id=row["id"],
        user_prompt=row.get("user_prompt", ""),
        scene_label=row.get("scene_label"),
        voice_output=row.get("voice_output", ""),
        polish_output=row.get("polish_output"),
        brain_output=row.get("brain_output"),
        word_count=row.get("word_count"),
        is_pinned=row.get("is_pinned", False),
        scene_order=row.get("scene_order"),
        created_at=row["created_at"],
    )


@router.delete("/{project_id}/scenes/{gen_id}")
async def delete_scene(
    project_id: str,
    gen_id: str,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict[str, bool]:
    """Delete a single scene (generation)."""
    _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    # Verify scene exists
    existing = (
        supabase.table("generations")
        .select("id")
        .eq("id", gen_id)
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Scene not found.",
        )

    try:
        supabase.table("generations").delete().eq("id", gen_id).eq(
            "user_id", user_id
        ).execute()
    except Exception as e:
        logger.error("[PROJECTS] Failed to delete scene %s: %s", gen_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete scene.",
        )

    logger.info("[PROJECTS] Deleted scene %s from project %s", gen_id, project_id)
    return {"deleted": True}


@router.post("/{project_id}/scenes/reorder")
async def reorder_scenes(
    project_id: str,
    reorder_request: ReorderRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> dict[str, bool | int]:
    """Bulk reorder scenes by setting scene_order based on list position."""
    _verify_project_ownership(project_id, user_id)
    supabase = get_supabase_client()

    # Verify all scene IDs belong to this project
    result = (
        supabase.table("generations")
        .select("id")
        .eq("project_id", project_id)
        .eq("user_id", user_id)
        .in_("id", reorder_request.scene_ids)
        .execute()
    )

    found_ids = {row["id"] for row in (result.data or [])}
    for sid in reorder_request.scene_ids:
        if sid not in found_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Scene {sid} not found in this project.",
            )

    # Update scene_order for each scene
    try:
        for idx, scene_id in enumerate(reorder_request.scene_ids):
            supabase.table("generations").update(
                {"scene_order": idx}
            ).eq("id", scene_id).eq("user_id", user_id).execute()
    except Exception as e:
        logger.error("[PROJECTS] Failed to reorder scenes: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reorder scenes.",
        )

    logger.info(
        "[PROJECTS] Reordered %d scenes in project %s",
        len(reorder_request.scene_ids),
        project_id,
    )
    return {"reordered": True, "count": len(reorder_request.scene_ids)}
