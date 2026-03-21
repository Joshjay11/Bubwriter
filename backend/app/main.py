"""BUB Writer API — FastAPI application entry point.

Configures CORS, registers all routers, and exposes the
health check at /api/health.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import (
    analyze_free,
    billing,
    brainstorm,
    conversation_import,
    generation,
    health,
    projects,
    voice_discovery,
    voice_profiles,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BUB Writer API")

# CORS — allow the frontend origin(s) defined in env
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register all routers under /api
app.include_router(health.router, prefix="/api")
app.include_router(voice_discovery.router, prefix="/api")
app.include_router(conversation_import.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(generation.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(analyze_free.router, prefix="/api")
app.include_router(voice_profiles.router, prefix="/api")
app.include_router(brainstorm.router, prefix="/api")
