"""
Skills router - handles CRUD operations for skills configuration.
"""

import sys
from pathlib import Path
from typing import Any, Dict
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from config_manager import ConfigManager

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

router = APIRouter()


class SkillUpdateRequest(BaseModel):
    skill: Dict[str, Any]


def _parse_markdown_skill(raw: str) -> Dict[str, Any]:
    """Parse a skill markdown with YAML frontmatter."""
    text = (raw or "").strip()
    if not text.startswith("---"):
        return {}

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}

    frontmatter_text = "\n".join(lines[1:end_idx]).strip()
    body_text = "\n".join(lines[end_idx + 1 :]).strip()

    parsed: Dict[str, Any] = {}
    try:
        fm = yaml.safe_load(frontmatter_text) if frontmatter_text else {}
        if isinstance(fm, dict):
            parsed.update(fm)
    except Exception:
        pass

    if body_text:
        parsed["content"] = body_text
    return parsed


def _to_skill_id(value: str) -> str:
    """Generate a safe skill id from user text."""
    v = re.sub(r"[^a-zA-Z0-9_]+", "_", (value or "").strip())
    v = re.sub(r"_+", "_", v).strip("_")
    return v.lower()


def _normalize_skill_payload(payload: Dict[str, Any], fallback_id: str = "") -> Dict[str, Any]:
    """Normalize skill payload to ensure required fields and markdown compatibility."""
    skill = dict(payload or {})
    markdown = skill.get("markdown") or skill.get("raw_markdown") or ""
    if isinstance(markdown, str) and markdown.strip():
        parsed = _parse_markdown_skill(markdown)
        # Frontmatter values apply only when field is missing from explicit form fields
        for k, v in parsed.items():
            if k not in skill or skill.get(k) in ("", None, {}, []):
                skill[k] = v
        skill["markdown"] = markdown.strip()

    if fallback_id:
        skill["id"] = fallback_id
    else:
        if not skill.get("id"):
            generated_id = _to_skill_id(str(skill.get("name", "")))
            if generated_id:
                skill["id"] = generated_id

    if not skill.get("name"):
        skill["name"] = skill.get("id", "")

    if "description" not in skill or skill["description"] is None:
        skill["description"] = ""
    if "enabled" not in skill:
        skill["enabled"] = True
    if not isinstance(skill.get("parameters"), dict):
        skill["parameters"] = {}

    return skill


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

    normalized_input = _normalize_skill_payload(request.skill, fallback_id=skill_id)

    updated = False
    for i, skill in enumerate(skills):
        if skill["id"] == skill_id:
            merged = {**skill, **normalized_input, "id": skill_id}
            skills[i] = _normalize_skill_payload(merged, fallback_id=skill_id)
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

    skill = _normalize_skill_payload(request.skill)
    if "id" not in skill or not skill["id"]:
        raise HTTPException(status_code=400, detail="Skill must have an 'id' field")
    if "name" not in skill or not str(skill["name"]).strip():
        raise HTTPException(status_code=400, detail="Skill must have a 'name' field")

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
