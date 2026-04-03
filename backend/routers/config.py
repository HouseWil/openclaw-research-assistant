"""
Config router - handles reading and updating OpenClaw configuration.
"""

import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from config_manager import ConfigManager

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

router = APIRouter()


class ConfigUpdateRequest(BaseModel):
    data: Dict[str, Any]


@router.get("/")
async def get_config():
    """Get the full OpenClaw configuration."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_openclaw_config()
    # Mask API key for security
    safe_cfg = dict(cfg)
    if "llm" in safe_cfg and "api_key" in safe_cfg["llm"]:
        key = safe_cfg["llm"]["api_key"]
        if key:
            safe_cfg["llm"] = dict(safe_cfg["llm"])
            safe_cfg["llm"]["api_key_masked"] = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
    return safe_cfg


@router.put("/")
async def update_config(request: ConfigUpdateRequest):
    """Update the OpenClaw configuration."""
    mgr = ConfigManager(CONFIG_DIR)
    current = mgr.get_openclaw_config()

    # Deep merge
    def deep_merge(base: dict, updates: dict) -> dict:
        result = dict(base)
        for k, v in updates.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = deep_merge(result[k], v)
            else:
                result[k] = v
        return result

    updated = deep_merge(current, request.data)
    mgr.save_openclaw_config(updated)
    return {"status": "ok", "message": "Configuration updated successfully"}


@router.post("/test-connection")
async def test_connection():
    """Test the LLM API connection with current config."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_openclaw_config()
    llm_cfg = cfg.get("llm", {})

    provider = llm_cfg.get("provider", "openai")
    api_key = llm_cfg.get("api_key", "")
    api_base = llm_cfg.get("api_base", "")
    model = llm_cfg.get("model", "gpt-4o")

    if not api_key:
        raise HTTPException(status_code=400, detail="API key not configured")

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            response = await client.messages.create(
                model=model,
                messages=[{"role": "user", "content": "Hello, respond with just 'OK'."}],
                max_tokens=10,
            )
            return {"status": "ok", "message": f"Connected to {provider}", "response": response.content[0].text}
        else:
            from openai import AsyncOpenAI
            kwargs = {"api_key": api_key}
            if api_base:
                kwargs["base_url"] = api_base
            client = AsyncOpenAI(**kwargs)
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "Hello, respond with just 'OK'."}],
                max_tokens=10,
            )
            return {"status": "ok", "message": f"Connected to {provider}", "response": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")
