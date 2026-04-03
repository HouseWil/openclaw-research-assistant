"""
Agents router - handles CRUD operations for agents configuration.
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


class AgentUpdateRequest(BaseModel):
    agent: Dict[str, Any]


@router.get("/")
async def get_agents():
    """Get all configured agents."""
    mgr = ConfigManager(CONFIG_DIR)
    return mgr.get_agents()


@router.put("/{agent_id}")
async def update_agent(agent_id: str, request: AgentUpdateRequest):
    """Update a specific agent by ID."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_agents()
    agents = cfg.get("agents", [])

    updated = False
    for i, agent in enumerate(agents):
        if agent["id"] == agent_id:
            agents[i] = {**agent, **request.agent, "id": agent_id}
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    cfg["agents"] = agents
    mgr.save_agents(cfg)
    return {"status": "ok", "message": f"Agent '{agent_id}' updated"}


@router.post("/")
async def create_agent(request: AgentUpdateRequest):
    """Create a new agent."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_agents()
    agents = cfg.get("agents", [])

    agent = request.agent
    if "id" not in agent:
        raise HTTPException(status_code=400, detail="Agent must have an 'id' field")

    # Check for duplicate ID
    for existing in agents:
        if existing["id"] == agent["id"]:
            raise HTTPException(status_code=409, detail=f"Agent with id '{agent['id']}' already exists")

    agents.append(agent)
    cfg["agents"] = agents
    mgr.save_agents(cfg)
    return {"status": "ok", "message": "Agent created", "agent": agent}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """Delete an agent by ID."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_agents()
    agents = cfg.get("agents", [])

    original_len = len(agents)
    agents = [a for a in agents if a["id"] != agent_id]

    if len(agents) == original_len:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")

    cfg["agents"] = agents
    mgr.save_agents(cfg)
    return {"status": "ok", "message": f"Agent '{agent_id}' deleted"}
