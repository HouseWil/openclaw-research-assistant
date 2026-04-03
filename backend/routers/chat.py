"""
Chat router - handles LLM chat requests with streaming support.
"""

import sys
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import json

sys.path.insert(0, str(Path(__file__).parent.parent))
from config_manager import ConfigManager
from models import ChatRequest

BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

router = APIRouter()


def _get_llm_config():
    mgr = ConfigManager(CONFIG_DIR)
    cfg = mgr.get_openclaw_config()
    return cfg.get("llm", {})


def _get_agent_config(agent_id: str):
    mgr = ConfigManager(CONFIG_DIR)
    agents_cfg = mgr.get_agents()
    for agent in agents_cfg.get("agents", []):
        if agent["id"] == agent_id and agent.get("enabled", True):
            return agent
    return None


def _get_skill_map():
    mgr = ConfigManager(CONFIG_DIR)
    skills_cfg = mgr.get_skills()
    return {s.get("id"): s for s in skills_cfg.get("skills", []) if isinstance(s, dict) and s.get("id")}


def _build_skills_prompt(agent: dict) -> str:
    skill_ids = [s for s in (agent.get("skills") or []) if isinstance(s, str) and s.strip()]
    if not skill_ids:
        return ""

    skill_map = _get_skill_map()
    enabled_skills = []
    for sid in skill_ids:
        sk = skill_map.get(sid)
        if not sk or sk.get("enabled") is False:
            continue
        enabled_skills.append(sk)

    if not enabled_skills:
        return ""

    sections = ["\n\n可用技能（按需使用，优先遵守每个技能说明）："]
    for sk in enabled_skills:
        header = f"- {sk.get('name') or sk.get('id')} ({sk.get('id')})"
        lines = [header]
        if sk.get("description"):
            lines.append(f"  描述: {sk.get('description')}")
        params = sk.get("parameters")
        if isinstance(params, dict) and params:
            lines.append(f"  参数: {json.dumps(params, ensure_ascii=False)}")
        if sk.get("markdown"):
            lines.append("  技能文档:")
            for ln in str(sk.get("markdown")).splitlines():
                lines.append("  " + ln)
        elif sk.get("content"):
            lines.append("  技能文档:")
            for ln in str(sk.get("content")).splitlines():
                lines.append("  " + ln)
        sections.append("\n".join(lines))

    return "\n".join(sections)


async def _stream_openai(client, model: str, messages: list, temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
    """Stream responses from OpenAI-compatible API."""
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {json.dumps({'content': delta.content, 'done': False})}\n\n"
        yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': type(e).__name__, 'done': True})}\n\n"


async def _stream_anthropic(client, model: str, messages: list, system_prompt: str, temperature: float, max_tokens: int) -> AsyncGenerator[str, None]:
    """Stream responses from Anthropic API."""
    try:
        anthropic_messages = [m for m in messages if m["role"] != "system"]
        kwargs = {
            "model": model,
            "messages": anthropic_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield f"data: {json.dumps({'content': text, 'done': False})}\n\n"
        yield f"data: {json.dumps({'content': '', 'done': True})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': type(e).__name__, 'done': True})}\n\n"


@router.post("/")
async def chat(request: ChatRequest):
    """Send a chat message and get a response (streaming or non-streaming)."""
    llm_cfg = _get_llm_config()

    provider = llm_cfg.get("provider", "openai")
    api_key = llm_cfg.get("api_key", "")
    api_base = llm_cfg.get("api_base", "")
    model = request.model or llm_cfg.get("model", "gpt-4o")
    temperature = request.temperature if request.temperature is not None else llm_cfg.get("temperature", 0.7)
    max_tokens = request.max_tokens or llm_cfg.get("max_tokens", 2048)
    do_stream = request.stream if request.stream is not None else llm_cfg.get("stream", True)

    if not api_key:
        raise HTTPException(status_code=400, detail="API key not configured. Please set it in Configuration.")

    # Build messages list
    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    # Inject agent system prompt if agent_id provided
    system_prompt = ""
    if request.agent_id:
        agent = _get_agent_config(request.agent_id)
        if agent:
            system_prompt = agent.get("system_prompt", "")
            system_prompt += _build_skills_prompt(agent)
            if agent.get("model"):
                model = agent["model"]
            temperature = agent.get("temperature", temperature)
            max_tokens = agent.get("max_tokens", max_tokens)

    if system_prompt:
        # Prepend system message if not already present
        if not messages or messages[0]["role"] != "system":
            messages = [{"role": "system", "content": system_prompt}] + messages

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.AsyncAnthropic(api_key=api_key)
            if do_stream:
                return StreamingResponse(
                    _stream_anthropic(client, model, messages, system_prompt, temperature, max_tokens),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            else:
                anthropic_messages = [m for m in messages if m["role"] != "system"]
                kwargs = {"model": model, "messages": anthropic_messages, "temperature": temperature, "max_tokens": max_tokens}
                if system_prompt:
                    kwargs["system"] = system_prompt
                response = await client.messages.create(**kwargs)
                return {"content": response.content[0].text, "model": model}
        else:
            # OpenAI or OpenAI-compatible
            from openai import AsyncOpenAI
            kwargs = {"api_key": api_key}
            if api_base:
                kwargs["base_url"] = api_base
            client = AsyncOpenAI(**kwargs)

            if do_stream:
                return StreamingResponse(
                    _stream_openai(client, model, messages, temperature, max_tokens),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            else:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return {"content": response.choices[0].message.content, "model": model}

    except Exception as e:
        raise HTTPException(status_code=500, detail="LLM API error: " + type(e).__name__)


@router.get("/models")
async def list_models():
    """List available models for the configured provider."""
    llm_cfg = _get_llm_config()
    provider = llm_cfg.get("provider", "openai")

    model_lists = {
        "openai": [
            {"id": "gpt-4o", "name": "GPT-4o"},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
            {"id": "gpt-4", "name": "GPT-4"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
        ],
        "anthropic": [
            {"id": "claude-opus-4-5", "name": "Claude Opus 4.5"},
            {"id": "claude-sonnet-4-5", "name": "Claude Sonnet 4.5"},
            {"id": "claude-haiku-4-5", "name": "Claude Haiku 4.5"},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
            {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku"},
        ],
        "custom": [
            {"id": "custom", "name": "Custom Model (set in config)"},
        ],
    }

    return {
        "provider": provider,
        "models": model_lists.get(provider, model_lists["openai"]),
        "current_model": llm_cfg.get("model", "gpt-4o"),
    }
