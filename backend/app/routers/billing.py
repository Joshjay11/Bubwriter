"""Billing router — placeholder for Stripe subscription endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/status")
async def billing_status() -> dict[str, str]:
    """Placeholder endpoint to verify routing works."""
    return {"status": "not_implemented", "router": "billing"}
