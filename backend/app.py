"""
OpenClaw Research Assistant - Main FastAPI Application
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

# Add backend directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config_manager import ConfigManager
from routers import chat, config, skills, agents

BASE_DIR = Path(__file__).parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
CONFIG_DIR = BASE_DIR / "config"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure config directory exists with defaults
    config_mgr = ConfigManager(CONFIG_DIR)
    config_mgr.ensure_defaults()

    yield


app = FastAPI(
    title="OpenClaw Research Assistant",
    description="AI-powered research assistant with configurable agents and skills",
    version="1.0.0",
    lifespan=lifespan,
)

# Include routers
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
app.include_router(agents.router, prefix="/api/agents", tags=["agents"])

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def root():
    """Serve the main frontend application."""
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "OpenClaw Research Assistant API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "openclaw-research-assistant"}
