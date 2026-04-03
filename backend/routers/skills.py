"""
Skills router - handles CRUD operations for skills configuration.
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


class SkillUpdateRequest(BaseModel):
    skill: Dict[str, Any]


@router.get("/")
async def get_skills():
    """Get all configured skills."""
    mgr = ConfigManager(CONFIG_DIR)
    return mgr.get_skills()


@router.put("/{skill_id}")
async def update_skill(skill_id: str, request: SkillUpdateRequest):
    """Update a specific skill by ID."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_skills()
    skills = cfg.get("skills", [])

    updated = False
    for i, skill in enumerate(skills):
        if skill["id"] == skill_id:
            skills[i] = {**skill, **request.skill, "id": skill_id}
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    cfg["skills"] = skills
    mgr.save_skills(cfg)
    return {"status": "ok", "message": f"Skill '{skill_id}' updated"}


@router.post("/")
async def create_skill(request: SkillUpdateRequest):
    """Create a new skill."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_skills()
    skills = cfg.get("skills", [])

    skill = request.skill
    if "id" not in skill:
        raise HTTPException(status_code=400, detail="Skill must have an 'id' field")

    # Check for duplicate ID
    for existing in skills:
        if existing["id"] == skill["id"]:
            raise HTTPException(status_code=409, detail=f"Skill with id '{skill['id']}' already exists")

    skills.append(skill)
    cfg["skills"] = skills
    mgr.save_skills(cfg)
    return {"status": "ok", "message": "Skill created", "skill": skill}


@router.delete("/{skill_id}")
async def delete_skill(skill_id: str):
    """Delete a skill by ID."""
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_skills()
    skills = cfg.get("skills", [])

    original_len = len(skills)
    skills = [s for s in skills if s["id"] != skill_id]

    if len(skills) == original_len:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    cfg["skills"] = skills
    mgr.save_skills(cfg)
    return {"status": "ok", "message": f"Skill '{skill_id}' deleted"}
