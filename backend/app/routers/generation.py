"""Generation router — Brain -> Voice -> Polish pipeline endpoints.

POST /api/generate          — Full pipeline (SSE streaming)
POST /api/generate/continue — Continue from previous generation
POST /api/generate/refine   — Re-run Voice with user feedback
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.models.generation_schemas import (
    ContinueRequest,
    GenerateRequest,
    RefineRequest,
)
from app.services.generation_pipeline import (
    build_continuation_context,
    run_generation_pipeline,
    run_refine_pipeline,
)
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate", tags=["generation"])


async def _load_voice_profile(
    voice_profile_id: str, user_id: str
) -> dict:
    """Load a voice profile from Supabase, verifying ownership."""
    supabase = get_supabase_client()
    result = (
        supabase.table("voice_profiles")
        .select("id, voice_instruction, anti_slop")
        .eq("id", voice_profile_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Voice profile not found.",
        )
    profile = result.data[0]
    if not profile.get("voice_instruction"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Voice profile has no compiled voice instruction. Complete Voice Discovery first.",
        )
    return profile


async def _load_project(
    project_id: str, user_id: str
) -> dict:
    """Load a project from Supabase, verifying ownership."""
    supabase = get_supabase_client()
    result = (
        supabase.table("projects")
        .select("id, title, genre, story_bible")
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


@router.post("")
async def generate_scene(
    generate_request: GenerateRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> StreamingResponse:
    """Run the full Brain -> Voice -> Polish pipeline (SSE streaming)."""
    # Load voice profile
    profile = await _load_voice_profile(generate_request.voice_profile_id, user_id)

    # Load project if specified
    project = None
    if generate_request.project_id:
        project = await _load_project(generate_request.project_id, user_id)

    # Load previous output for continuation
    previous_output = None
    if generate_request.previous_scene_id:
        supabase = get_supabase_client()
        prev_result = (
            supabase.table("generations")
            .select("voice_output")
            .eq("id", generate_request.previous_scene_id)
            .eq("user_id", user_id)
            .execute()
        )
        if prev_result.data and prev_result.data[0].get("voice_output"):
            previous_output = prev_result.data[0]["voice_output"]

    return StreamingResponse(
        run_generation_pipeline(
            user_id=user_id,
            prompt=generate_request.prompt,
            voice_instruction=profile["voice_instruction"],
            anti_slop=profile.get("anti_slop"),
            project=project,
            include_polish=generate_request.include_polish,
            previous_output=previous_output,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/continue")
async def continue_scene(
    continue_request: ContinueRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> StreamingResponse:
    """Continue from a previous generation."""
    # Load voice profile
    profile = await _load_voice_profile(continue_request.voice_profile_id, user_id)

    # Load previous generation's output
    supabase = get_supabase_client()
    prev_result = (
        supabase.table("generations")
        .select("voice_output, project_id")
        .eq("id", continue_request.generation_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not prev_result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Previous generation not found.",
        )

    previous_output = prev_result.data[0].get("voice_output", "")
    project_id = continue_request.project_id or prev_result.data[0].get("project_id")

    # Load project if we have one
    project = None
    if project_id:
        project = await _load_project(project_id, user_id)

    prompt = continue_request.prompt or "Continue the scene from where it left off."

    return StreamingResponse(
        run_generation_pipeline(
            user_id=user_id,
            prompt=prompt,
            voice_instruction=profile["voice_instruction"],
            anti_slop=profile.get("anti_slop"),
            project=project,
            include_polish=continue_request.include_polish,
            previous_output=previous_output,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/refine")
async def refine_scene(
    refine_request: RefineRequest,
    user_id: Annotated[str, Depends(get_current_user)],
) -> StreamingResponse:
    """Re-run Voice with user feedback, reusing the Brain skeleton."""
    # Load voice profile
    profile = await _load_voice_profile(refine_request.voice_profile_id, user_id)

    return StreamingResponse(
        run_refine_pipeline(
            user_id=user_id,
            generation_id=refine_request.generation_id,
            feedback=refine_request.feedback,
            voice_instruction=profile["voice_instruction"],
            anti_slop=profile.get("anti_slop"),
            include_polish=refine_request.include_polish,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
