#!/usr/bin/env python3
"""
OpenClaw Research Assistant - One-Click Installer

Usage:
    python install.py          # Interactive installation with web UI
    python install.py --skip   # Skip installer, start app directly

This script:
1. Checks Python version and dependencies
2. Installs required Python packages
3. Starts a web-based installation wizard on localhost
4. After user completes setup, starts the main application
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.resolve()
FRONTEND_DIR = BASE_DIR / "frontend"
CONFIG_DIR = BASE_DIR / "config"
BACKEND_DIR = BASE_DIR / "backend"
REQUIREMENTS_FILE = BASE_DIR / "requirements.txt"

INSTALLER_PORT = 8765
APP_PORT = 8000

# ──────────────────────────────────────────────
# ANSI colours
# ──────────────────────────────────────────────
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"


def cprint(msg, color=RESET):
    print(f"{color}{msg}{RESET}")


def banner():
    cprint(
        r"""
  ___                  ____ _
 / _ \ _ __   ___ _ __/ ___| | __ ___      __
| | | | '_ \ / _ \ '_ \___ \ |/ _` \ \ /\ / /
| |_| | |_) |  __/ | | |__) | | (_| |\ V  V /
 \___/| .__/ \___|_| |_|____/|_|\__,_| \_/\_/
      |_|
        科研助手 · 一键安装向导
""",
        CYAN,
    )


# ──────────────────────────────────────────────
# Dependency installation
# ──────────────────────────────────────────────
def check_python_version():
    """Ensure Python >= 3.9."""
    if sys.version_info < (3, 9):
        cprint(f"❌ 需要 Python 3.9+，当前版本: {sys.version}", RED)
        sys.exit(1)
    cprint(f"✅ Python {sys.version.split()[0]}", GREEN)


def install_dependencies():
    """Install Python packages from requirements.txt."""
    if not REQUIREMENTS_FILE.exists():
        cprint("⚠️  未找到 requirements.txt，跳过依赖安装", YELLOW)
        return

    cprint("\n📦 正在安装依赖包...", BLUE)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE), "-q"],
        capture_output=False,
    )
    if result.returncode != 0:
        cprint("❌ 依赖安装失败，请检查网络连接或手动运行:", RED)
        cprint(f"   pip install -r {REQUIREMENTS_FILE}", YELLOW)
        sys.exit(1)
    cprint("✅ 依赖安装完成", GREEN)


# ──────────────────────────────────────────────
# Config writing (called by installer API)
# ──────────────────────────────────────────────
def write_install_config(payload: dict):
    """Write YAML config files based on installer form data."""
    # Import here after packages are installed
    import yaml  # noqa: PLC0415

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # ── openclaw.yaml ──────────────────────────
    openclaw_cfg = {
        "app": {
            "name": "OpenClaw Research Assistant",
            "version": "1.0.0",
            "host": "127.0.0.1",
            "port": APP_PORT,
        },
        "llm": {
            "provider": payload.get("provider", "openai"),
            "api_key": payload.get("api_key", ""),
            "api_base": payload.get("api_base", ""),
            "model": payload.get("model", "gpt-4o"),
            "temperature": float(payload.get("temperature", 0.7)),
            "max_tokens": int(payload.get("max_tokens", 2048)),
            "stream": bool(payload.get("enable_streaming", True)),
        },
        "ui": {
            "theme": "light",
            "language": "zh-CN",
            "show_thinking": False,
        },
    }

    with open(CONFIG_DIR / "openclaw.yaml", "w", encoding="utf-8") as f:
        yaml.dump(openclaw_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ── skills.yaml ────────────────────────────
    from backend.config_manager import DEFAULT_SKILLS_CONFIG  # noqa: PLC0415

    skills_cfg = dict(DEFAULT_SKILLS_CONFIG)
    selected_skills = set(payload.get("selected_skills", []))
    for skill in skills_cfg["skills"]:
        skill["enabled"] = skill["id"] in selected_skills

    with open(CONFIG_DIR / "skills.yaml", "w", encoding="utf-8") as f:
        yaml.dump(skills_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # ── agents.yaml ────────────────────────────
    from backend.config_manager import DEFAULT_AGENTS_CONFIG  # noqa: PLC0415

    agents_cfg = dict(DEFAULT_AGENTS_CONFIG)
    selected_agents = set(payload.get("selected_agents", []))
    for agent in agents_cfg["agents"]:
        agent["enabled"] = agent["id"] in selected_agents

    with open(CONFIG_DIR / "agents.yaml", "w", encoding="utf-8") as f:
        yaml.dump(agents_cfg, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    cprint("✅ 配置文件写入完成", GREEN)


# ──────────────────────────────────────────────
# Minimal HTTP server for the installer UI
# ──────────────────────────────────────────────
_install_done = threading.Event()
_install_payload: dict = {}


class InstallerHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # silence default logging
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/installer.html"):
            self._serve_file(FRONTEND_DIR / "installer.html", "text/html")
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/install":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                write_install_config(payload)
                global _install_payload
                _install_payload = payload
                resp = json.dumps({"status": "ok", "app_url": f"http://127.0.0.1:{APP_PORT}/"})
                self._json_response(200, resp)
                _install_done.set()
            except Exception as exc:
                resp = json.dumps({"detail": str(exc)})
                self._json_response(500, resp)
        else:
            self.send_error(404)

    def _serve_file(self, path: Path, mime: str):
        if not path.exists():
            self.send_error(404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _json_response(self, code: int, body: str):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(data))
        self.end_headers()
        self.wfile.write(data)


def run_installer_server():
    """Run the installer HTTP server until installation is complete."""
    installer_url = f"http://127.0.0.1:{INSTALLER_PORT}/"
    cprint(f"\n🌐 安装向导已启动: {installer_url}", GREEN)
    cprint("   正在打开浏览器...", BLUE)

    server = HTTPServer(("127.0.0.1", INSTALLER_PORT), InstallerHandler)
    server.timeout = 1

    def _open_browser():
        time.sleep(1.0)
        webbrowser.open(installer_url)

    threading.Thread(target=_open_browser, daemon=True).start()

    while not _install_done.is_set():
        server.handle_request()

    server.server_close()
    cprint("✅ 安装配置完成", GREEN)


# ──────────────────────────────────────────────
# Start the main FastAPI application
# ──────────────────────────────────────────────
def start_app():
    """Launch the FastAPI backend server."""
    try:
        import uvicorn  # noqa: PLC0415
    except ImportError:
        cprint("❌ uvicorn 未安装，请先运行: pip install uvicorn", RED)
        sys.exit(1)

    app_url = f"http://127.0.0.1:{APP_PORT}/"
    cprint(f"\n🚀 启动 OpenClaw 应用: {app_url}", GREEN)

    def _open_app():
        time.sleep(1.5)
        webbrowser.open(app_url)

    threading.Thread(target=_open_app, daemon=True).start()

    # Change to base dir so relative paths resolve correctly
    os.chdir(BASE_DIR)
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",
        port=APP_PORT,
        reload=False,
        log_level="warning",
    )


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="OpenClaw Research Assistant Installer")
    parser.add_argument("--skip", action="store_true", help="Skip installer, start app directly")
    args = parser.parse_args()

    banner()
    check_python_version()
    install_dependencies()

    if args.skip or (CONFIG_DIR / "openclaw.yaml").exists():
        cprint("\n⚙️  检测到已有配置，跳过安装向导", BLUE)
        if not args.skip:
            cprint("   提示: 运行 'python install.py' 并删除 config/openclaw.yaml 可重新安装", YELLOW)
    else:
        run_installer_server()

    start_app()


if __name__ == "__main__":
    main()
