"""Voice profiles listing router — retrieve saved Voice DNA Profiles."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import get_current_user
from app.models.schemas import VoiceProfileListResponse
from app.services.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice-profiles", tags=["voice-profiles"])


@router.get("", response_model=VoiceProfileListResponse)
async def list_voice_profiles(
    user_id: Annotated[str, Depends(get_current_user)],
) -> VoiceProfileListResponse:
    """List all voice profiles for the authenticated user."""
    try:
        supabase = get_supabase_client()
        result = (
            supabase.table("voice_profiles")
            .select("id, profile_name, voice_summary, created_at, updated_at")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return VoiceProfileListResponse(profiles=result.data)
    except Exception as e:
        logger.error("Failed to list voice profiles: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to load profiles.",
        )
