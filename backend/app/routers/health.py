"""Health check endpoint — verifies the service is running."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """Return service status for uptime monitoring."""
    return {"status": "ok", "service": "bub-writer"}
