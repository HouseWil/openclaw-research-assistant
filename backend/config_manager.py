"""
Configuration manager for OpenClaw Research Assistant.
Reads and writes YAML configuration files.
"""

from pathlib import Path
from typing import Any, Dict
import yaml


DEFAULT_OPENCLAW_CONFIG = {
    "app": {
        "name": "OpenClaw Research Assistant",
        "version": "1.0.0",
        "host": "127.0.0.1",
        "port": 8000,
    },
    "llm": {
        "provider": "openai",
        "api_key": "",
        "api_base": "",
        "model": "gpt-4o",
        "temperature": 0.7,
        "max_tokens": 2048,
        "stream": True,
    },
    "ui": {
        "theme": "light",
        "language": "zh-CN",
        "show_thinking": False,
    },
}

DEFAULT_SKILLS_CONFIG = {
    "skills": [
        {
            "id": "web_search",
            "name": "网络搜索",
            "description": "搜索互联网获取最新信息",
            "enabled": False,
            "parameters": {
                "search_engine": "google",
                "max_results": 5,
            },
        },
        {
            "id": "paper_reader",
            "name": "论文阅读",
            "description": "解析和总结学术论文",
            "enabled": True,
            "parameters": {
                "supported_formats": ["pdf", "arxiv"],
                "summary_length": "medium",
            },
        },
        {
            "id": "code_executor",
            "name": "代码执行",
            "description": "执行 Python 代码片段",
            "enabled": False,
            "parameters": {
                "timeout": 30,
                "allowed_libraries": ["numpy", "pandas", "matplotlib"],
            },
        },
        {
            "id": "citation_manager",
            "name": "引用管理",
            "description": "管理和格式化学术引用",
            "enabled": True,
            "parameters": {
                "default_style": "APA",
                "supported_styles": ["APA", "MLA", "Chicago", "IEEE"],
            },
        },
    ]
}

DEFAULT_AGENTS_CONFIG = {
    "agents": [
        {
            "id": "research_assistant",
            "name": "科研助手",
            "description": "通用科研辅助智能体，帮助文献调研、实验设计和论文写作",
            "enabled": True,
            "model": "",
            "system_prompt": (
                "你是一位专业的科研助手，具备深厚的学术背景。"
                "你能够帮助研究人员进行文献调研、数据分析、论文写作和实验设计。"
                "请用专业、准确、简洁的语言回答问题，并在适当时引用相关文献。"
            ),
            "skills": ["paper_reader", "citation_manager"],
            "temperature": 0.7,
            "max_tokens": 2048,
        },
        {
            "id": "writing_assistant",
            "name": "论文写作助手",
            "description": "专注于学术写作，帮助改进论文结构、表达和引用",
            "enabled": True,
            "model": "",
            "system_prompt": (
                "你是一位专业的学术写作专家。"
                "你擅长帮助研究人员改进论文的结构、逻辑、语言表达和引用格式。"
                "请提供具体、可操作的写作建议，并保持学术严谨性。"
            ),
            "skills": ["citation_manager"],
            "temperature": 0.5,
            "max_tokens": 4096,
        },
        {
            "id": "data_analyst",
            "name": "数据分析助手",
            "description": "帮助分析实验数据，生成可视化和统计报告",
            "enabled": False,
            "model": "",
            "system_prompt": (
                "你是一位数据分析专家，擅长统计学和数据可视化。"
                "你能够帮助研究人员分析实验数据、选择合适的统计方法和解读结果。"
                "请提供清晰的分析步骤和代码示例。"
            ),
            "skills": ["code_executor"],
            "temperature": 0.3,
            "max_tokens": 2048,
        },
    ]
}


class ConfigManager:
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)
        self.openclaw_config_path = self.config_dir / "openclaw.yaml"
        self.skills_config_path = self.config_dir / "skills.yaml"
        self.agents_config_path = self.config_dir / "agents.yaml"

    def ensure_defaults(self):
        """Create default config files if they don't exist."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        if not self.openclaw_config_path.exists():
            self._write_yaml(self.openclaw_config_path, DEFAULT_OPENCLAW_CONFIG)
        if not self.skills_config_path.exists():
            self._write_yaml(self.skills_config_path, DEFAULT_SKILLS_CONFIG)
        if not self.agents_config_path.exists():
            self._write_yaml(self.agents_config_path, DEFAULT_AGENTS_CONFIG)

    def get_openclaw_config(self) -> Dict[str, Any]:
        return self._read_yaml(self.openclaw_config_path, DEFAULT_OPENCLAW_CONFIG)

    def save_openclaw_config(self, data: Dict[str, Any]) -> None:
        self._write_yaml(self.openclaw_config_path, data)

    def get_skills(self) -> Dict[str, Any]:
        return self._read_yaml(self.skills_config_path, DEFAULT_SKILLS_CONFIG)

    def save_skills(self, data: Dict[str, Any]) -> None:
        self._write_yaml(self.skills_config_path, data)

    def get_agents(self) -> Dict[str, Any]:
        return self._read_yaml(self.agents_config_path, DEFAULT_AGENTS_CONFIG)

    def save_agents(self, data: Dict[str, Any]) -> None:
        self._write_yaml(self.agents_config_path, data)

    def _read_yaml(self, path: Path, default: Dict) -> Dict[str, Any]:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if data is not None else default

    def _write_yaml(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
