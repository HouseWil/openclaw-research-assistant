"""
Gateway router - manage and monitor the local OpenClaw Gateway.
"""

import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))
from config_manager import ConfigManager
import gateway_manager

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

router = APIRouter()


def _get_gateway_cfg() -> dict:
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_openclaw_config()
    return cfg.get("gateway", {})


class GatewayConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    auto_start: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    password: Optional[str] = None
    openclaw_command: Optional[str] = None
    startup_timeout: Optional[int] = None
    health_check_interval: Optional[int] = None


@router.get("/status")
async def get_status():
    """Get current OpenClaw Gateway connection status."""
    cfg = _get_gateway_cfg()
    return gateway_manager.get_status(cfg)


@router.post("/start")
async def start_gateway():
    """Start the OpenClaw Gateway subprocess."""
    cfg = _get_gateway_cfg()
    if not cfg.get("enabled", False):
        raise HTTPException(status_code=400, detail="Gateway 功能未启用，请先在配置中启用")
    result = await asyncio.get_running_loop().run_in_executor(None, gateway_manager.start_gateway, cfg)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.post("/stop")
async def stop_gateway():
    """Stop the managed OpenClaw Gateway subprocess."""
    result = gateway_manager.stop_gateway()
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return result


@router.get("/config")
async def get_config():
    """Get Gateway configuration."""
    return _get_gateway_cfg()


@router.put("/config")
async def update_config(update: GatewayConfigUpdate):
    """Update Gateway configuration."""
    mgr = ConfigManager(CONFIG_DIR)
    full_cfg = mgr.get_openclaw_config()
    gateway_cfg = full_cfg.get("gateway", {})

    patch = update.model_dump(exclude_none=True)
    gateway_cfg.update(patch)
    full_cfg["gateway"] = gateway_cfg
    mgr.save_openclaw_config(full_cfg)
    return {"message": "Gateway 配置已更新", "config": gateway_cfg}
