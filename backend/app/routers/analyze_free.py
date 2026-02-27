"""DNA Analyzer router — public, no auth required. Rate-limited in production."""

from fastapi import APIRouter

router = APIRouter(prefix="/analyze-free", tags=["analyze-free"])


@router.get("/status")
async def analyze_free_status() -> dict[str, str]:
    """Placeholder endpoint to verify routing works."""
    return {"status": "not_implemented", "router": "analyze_free"}
