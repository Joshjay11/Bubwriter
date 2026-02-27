"""Projects router — placeholder for writing project endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/status")
async def projects_status() -> dict[str, str]:
    """Placeholder endpoint to verify routing works."""
    return {"status": "not_implemented", "router": "projects"}
