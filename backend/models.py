"""
Pydantic models for OpenClaw Research Assistant API.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: 'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message content")


class ChatRequest(BaseModel):
    messages: List[ChatMessage] = Field(..., description="Conversation history")
    agent_id: Optional[str] = Field(None, description="Agent ID to use (uses default config if None)")
    stream: Optional[bool] = Field(None, description="Override stream setting from config")
    model: Optional[str] = Field(None, description="Override model from config")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1)


class LLMConfig(BaseModel):
    provider: str = Field("openai", description="LLM provider: openai, anthropic, custom")
    api_key: str = Field("", description="API key for the LLM provider")
    api_base: str = Field("", description="Custom API base URL (for local models)")
    model: str = Field("gpt-4o", description="Model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1)
    stream: bool = Field(True, description="Enable streaming responses")


class AppConfig(BaseModel):
    name: str = "OpenClaw Research Assistant"
    version: str = "1.0.0"
    host: str = "127.0.0.1"
    port: int = 8000


class UIConfig(BaseModel):
    theme: str = "light"
    language: str = "zh-CN"
    show_thinking: bool = False


class OpenClawConfig(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


class SkillParameter(BaseModel):
    name: str
    value: Any


class Skill(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    parameters: Dict[str, Any] = Field(default_factory=dict)


class SkillsConfig(BaseModel):
    skills: List[Skill] = Field(default_factory=list)


class Agent(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool = True
    model: str = ""
    system_prompt: str = ""
    skills: List[str] = Field(default_factory=list)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(2048, ge=1)


class AgentsConfig(BaseModel):
    agents: List[Agent] = Field(default_factory=list)


class InstallRequest(BaseModel):
    provider: str = "openai"
    api_key: str
    api_base: str = ""
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2048
    theme: str = "light"
    language: str = "zh-CN"
    enable_streaming: bool = True
    selected_skills: List[str] = Field(default_factory=list)
    selected_agents: List[str] = Field(default_factory=list)
