"""Generation router — placeholder for the Brain->Voice->Polish pipeline."""

from fastapi import APIRouter

router = APIRouter(prefix="/generate", tags=["generation"])


@router.get("/status")
async def generation_status() -> dict[str, str]:
    """Placeholder endpoint to verify routing works."""
    return {"status": "not_implemented", "router": "generation"}
