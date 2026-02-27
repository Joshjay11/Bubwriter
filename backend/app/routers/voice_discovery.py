"""Voice Discovery router — placeholder for voice DNA analysis endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/voice-discovery", tags=["voice-discovery"])


@router.get("/status")
async def voice_discovery_status() -> dict[str, str]:
    """Placeholder endpoint to verify routing works."""
    return {"status": "not_implemented", "router": "voice_discovery"}
