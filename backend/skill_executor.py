"""
Generic skill execution and tool schema helpers.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# Default outbound allowlist to reduce SSRF risk.
DEFAULT_ALLOWED_DOMAINS = {"wttr.in", "api.open-meteo.com"}
MAX_RESULT_CHARS = 4000
MAX_ARG_CHARS = 500


class SkillExecutionError(Exception):
    """Raised when a skill cannot be executed safely or successfully."""


def _clamp_int(value: Any, default: int, min_v: int, max_v: int) -> int:
    try:
        iv = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_v, min(max_v, iv))


def _safe_json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _render_template(value: Any, args: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        try:
            return value.format(**args)
        except Exception:
            return value
    if isinstance(value, dict):
        return {k: _render_template(v, args) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_template(v, args) for v in value]
    return value


def _extract_path(data: Any, path: str) -> Any:
    cur = data
    for part in [p for p in str(path).split(".") if p]:
        if isinstance(cur, list):
            try:
                idx = int(part)
            except ValueError:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        elif isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        else:
            return None
    return cur


def _validate_tool_args(args: Dict[str, Any]) -> None:
    for k, v in (args or {}).items():
        if isinstance(v, str) and len(v) > MAX_ARG_CHARS:
            raise SkillExecutionError(f"Argument '{k}' is too long")


def _get_allowed_domains(execution: Dict[str, Any]) -> set[str]:
    configured = execution.get("allowed_domains")
    if isinstance(configured, list):
        cleaned = {str(x).strip().lower() for x in configured if str(x).strip()}
        if cleaned:
            return cleaned
    return set(DEFAULT_ALLOWED_DOMAINS)


def _validate_target(url: str, allowed_domains: set[str]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        raise SkillExecutionError("Only http/https skill endpoints are allowed")
    if not host:
        raise SkillExecutionError("Invalid skill endpoint host")
    if host not in allowed_domains:
        raise SkillExecutionError(f"Endpoint host '{host}' is not in allowlist")


def build_openai_tool(skill: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a skill config into an OpenAI function tool schema."""
    skill_id = str(skill.get("id") or "").strip()
    if not skill_id:
        raise ValueError("Skill id is required")

    arg_schema = skill.get("arg_schema")
    # Keep validation lightweight here: enforce object/properties shape only.
    # Full JSON Schema validation is intentionally omitted for compatibility.
    has_valid_schema = isinstance(arg_schema, dict) and isinstance(arg_schema.get("properties"), dict)
    if not has_valid_schema:
        params = skill.get("parameters") if isinstance(skill.get("parameters"), dict) else {}
        arg_schema = {
            "type": "object",
            "properties": {k: {"type": "string", "description": f"参数: {k}"} for k in params.keys()},
            "required": [],
        }

    if arg_schema.get("type") != "object":
        arg_schema["type"] = "object"
    arg_schema.setdefault("properties", {})
    arg_schema.setdefault("required", [])

    return {
        "type": "function",
        "function": {
            "name": skill_id,
            "description": skill.get("description") or skill.get("name") or skill_id,
            "parameters": arg_schema,
        },
    }


def collect_executable_skills(agent: Dict[str, Any], skill_map: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Collect enabled skills linked by an agent and having execution config."""
    out: List[Dict[str, Any]] = []
    for sid in [s for s in (agent.get("skills") or []) if isinstance(s, str) and s.strip()]:
        sk = skill_map.get(sid)
        if not sk or sk.get("enabled") is False:
            continue
        if isinstance(sk.get("execution"), dict):
            out.append(sk)
    return out


async def execute_skill(skill: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a generic HTTP skill and return normalized output."""
    skill_id = str(skill.get("id") or "")
    execution = skill.get("execution")
    if not isinstance(execution, dict):
        raise SkillExecutionError(f"Skill '{skill_id}' has no execution config")

    if str(execution.get("type") or "http").lower() != "http":
        raise SkillExecutionError("Only execution.type=http is currently supported")

    if not isinstance(args, dict):
        args = {}
    _validate_tool_args(args)

    method = str(execution.get("method") or "GET").upper()
    endpoint_tpl = execution.get("endpoint")
    if not endpoint_tpl:
        raise SkillExecutionError("Skill execution endpoint is required")
    endpoint = _render_template(endpoint_tpl, args)
    if not isinstance(endpoint, str):
        endpoint = str(endpoint)

    allowed = _get_allowed_domains(execution)
    _validate_target(endpoint, allowed)

    timeout = _clamp_int(execution.get("timeout_seconds"), default=10, min_v=1, max_v=30)
    retries = _clamp_int(execution.get("retries"), default=1, min_v=0, max_v=2)

    headers = _render_template(execution.get("headers") or {}, args)
    query = _render_template(execution.get("query") or {}, args)
    body = _render_template(execution.get("body") or None, args)

    start = time.perf_counter()
    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(
                    method=method,
                    url=endpoint,
                    headers=headers if isinstance(headers, dict) else None,
                    params=query if isinstance(query, dict) else None,
                    json=body if isinstance(body, (dict, list)) else None,
                )
                response.raise_for_status()
            break
        except Exception as exc:
            if attempt >= retries:
                elapsed = (time.perf_counter() - start) * 1000
                logger.warning("skill_execute_failed skill=%s ms=%.1f err=%s", skill_id, elapsed, type(exc).__name__)
                raise SkillExecutionError(f"HTTP request failed: {type(exc).__name__}") from exc

    content_type = response.headers.get("content-type", "")
    parsed: Any
    if "application/json" in content_type:
        try:
            parsed = response.json()
        except Exception:
            parsed = response.text
    else:
        parsed = response.text

    result: Any = parsed
    result_path = execution.get("result_path")
    if result_path:
        extracted = _extract_path(parsed, str(result_path))
        if extracted is not None:
            result = extracted

    result_template = execution.get("result_template")
    if isinstance(result_template, str) and result_template.strip():
        rendered = _render_template(result_template, {"result": result, **args})
        output_text = rendered if isinstance(rendered, str) else _safe_json_dumps(rendered)
    else:
        output_text = result if isinstance(result, str) else _safe_json_dumps(result)

    output_text = _truncate(str(output_text))
    elapsed = (time.perf_counter() - start) * 1000
    logger.info("skill_execute_ok skill=%s ms=%.1f", skill_id, elapsed)
    return {
        "skill_id": skill_id,
        "ok": True,
        "output": output_text,
    }
