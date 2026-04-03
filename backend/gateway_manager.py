"""
Gateway Manager - manages the local OpenClaw Gateway process lifecycle.
"""

import asyncio
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Singleton process handle
_gateway_process: Optional[subprocess.Popen] = None

# Substrings that indicate the openclaw binary exited due to a stale lock file.
_STALE_LOCK_MARKERS = ("already running", "lock timeout")

# Seconds to wait after clearing a stale lock before retrying startup.
# Gives the OS time to fully release any resources held by the previous process.
_STALE_LOCK_RETRY_DELAY = 1.0


def _get_gateway_url(cfg: dict) -> str:
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 18789)
    return f"http://{host}:{port}"


def _get_canvas_url(cfg: dict) -> str:
    """Return the URL of the Gateway's built-in canvas web UI."""
    return _get_gateway_url(cfg) + "/__openclaw__/canvas/"


def is_running(cfg: dict) -> bool:
    """Check whether the Gateway canvas HTTP endpoint is reachable."""
    url = _get_canvas_url(cfg)
    try:
        with httpx.Client(timeout=2.0) as client:
            resp = client.get(url)
            return 200 <= resp.status_code < 300
    except Exception:
        return False


def _try_clear_stale_lock(command: str) -> None:
    """
    Attempt to clear a stale gateway lock by running ``openclaw gateway stop``.

    The openclaw binary maintains a lock/pid file to prevent duplicate
    instances.  When a previous gateway process crashes without cleaning up,
    the next ``openclaw gateway run`` invocation exits immediately with
    "gateway already running; lock timeout".  Invoking ``openclaw gateway
    stop`` removes the stale lock so the gateway can be started again.
    """
    try:
        subprocess.run(
            [command, "gateway", "stop"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
    except Exception:
        pass


def _resolve_command(command: str) -> str:
    """
    Resolve a command name to its full executable path.

    When the web server's PATH differs from the user's interactive shell PATH
    (e.g. the binary is installed inside a virtual-environment that the web
    process did not activate), ``subprocess.Popen`` would raise
    ``FileNotFoundError`` even though the command works fine in a terminal.

    Resolution order:
    1. If *command* is already an absolute path, use it as-is.
    2. ``shutil.which()`` searches the PATH inherited by the current process.
    3. The ``bin/`` (or ``Scripts/`` on Windows) directory that contains the
       running Python interpreter – covers venv / pipx installs.
    4. Fall back to the original *command* string and let the OS report the
       error with a meaningful message.
    """
    # Already absolute – trust the caller.
    if Path(command).is_absolute():
        return command

    # Standard PATH lookup.
    found = shutil.which(command)
    if found:
        return found

    # Same directory as the current Python interpreter (handles venv installs).
    python_bin_dir = Path(sys.executable).parent
    exe_suffix = ".exe" if sys.platform == "win32" else ""
    cmd_name = command if command.lower().endswith(exe_suffix) else command + exe_suffix
    candidate = python_bin_dir / cmd_name
    if candidate.is_file():
        return str(candidate)

    # Give up – return the original name so the OS error message is helpful.
    return command


def start_gateway(cfg: dict) -> dict:
    """
    Start the OpenClaw Gateway as a subprocess (if not already running).
    Returns a dict with keys: success (bool), message (str).

    If the openclaw binary exits immediately with a stale-lock error
    ("gateway already running / lock timeout"), this function will
    automatically run ``openclaw gateway stop`` to clear the lock and
    retry once.
    """
    return _start_gateway_impl(cfg, allow_stale_lock_retry=True)


def _start_gateway_impl(cfg: dict, allow_stale_lock_retry: bool) -> dict:
    """Internal implementation of gateway startup with optional stale-lock retry."""
    global _gateway_process

    if is_running(cfg):
        return {"success": True, "message": "Gateway 已经在运行中"}

    command = _resolve_command(cfg.get("openclaw_command", "openclaw"))
    host = cfg.get("host", "127.0.0.1")
    port = cfg.get("port", 18789)
    timeout = int(cfg.get("startup_timeout", 30))

    cmd = [command, "gateway", "run", "--port", str(port)]
    password = cfg.get("password", "")
    if password:
        cmd += ["--password", password]

    try:
        _gateway_process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            **({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == "win32" else {"start_new_session": True}),
        )
    except FileNotFoundError:
        return {"success": False, "message": f"找不到 Gateway 命令: {command}，请检查配置"}
    except Exception as exc:
        return {"success": False, "message": f"启动 Gateway 失败: {exc}"}

    def _read_stderr() -> str:
        try:
            _, err = _gateway_process.communicate(timeout=1)
            return err.decode(errors="replace") if err else ""
        except Exception:
            return ""

    def _handle_unexpected_exit(stderr_text: str) -> dict:
        """Handle early process exit; retry once on stale-lock errors."""
        if allow_stale_lock_retry and any(m in stderr_text.lower() for m in _STALE_LOCK_MARKERS):
            # The binary exited because of a lock conflict.  Before we clear
            # the lock (which stops any running gateway), check whether the
            # gateway is actually reachable.  This handles the race where the
            # binary exits due to a lock held by a live, fully-started gateway
            # process — clearing the lock in that case would kill the user's
            # running gateway unnecessarily.
            if is_running(cfg):
                logger.info(
                    "Gateway reported a lock conflict but the canvas endpoint is "
                    "reachable; treating as already running."
                )
                return {"success": True, "message": "Gateway 已经在运行中"}
            logger.warning(
                "Gateway exited with a stale-lock error; running 'openclaw gateway stop' "
                "to clear the lock and retrying. stderr: %s",
                stderr_text.strip(),
            )
            _try_clear_stale_lock(command)
            time.sleep(_STALE_LOCK_RETRY_DELAY)
            return _start_gateway_impl(cfg, allow_stale_lock_retry=False)
        return {"success": False, "message": f"Gateway 进程意外退出: {stderr_text[:200]}"}

    # Wait until the gateway is reachable
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if is_running(cfg):
            # Brief stabilisation pause: confirm the gateway stays up and is not
            # just transiently alive during initialisation.
            time.sleep(1.0)
            if _gateway_process.poll() is not None:
                return _handle_unexpected_exit(_read_stderr())
            return {"success": True, "message": "Gateway 已成功启动"}
        if _gateway_process.poll() is not None:
            return _handle_unexpected_exit(_read_stderr())
        time.sleep(0.5)

    return {"success": False, "message": f"Gateway 在 {timeout} 秒内未能启动"}


def stop_gateway() -> dict:
    """Stop the managed Gateway subprocess (if any)."""
    global _gateway_process

    if _gateway_process is None:
        return {"success": True, "message": "没有受管理的 Gateway 进程"}

    try:
        _gateway_process.terminate()
        try:
            _gateway_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _gateway_process.kill()
            _gateway_process.wait(timeout=3)
        _gateway_process = None
        return {"success": True, "message": "Gateway 已停止"}
    except Exception as exc:
        return {"success": False, "message": f"停止 Gateway 失败: {exc}"}


def get_status(cfg: dict) -> dict:
    """Return current gateway status information."""
    running = is_running(cfg)
    managed = _gateway_process is not None and _gateway_process.poll() is None
    return {
        "running": running,
        "managed": managed,
        "host": cfg.get("host", "127.0.0.1"),
        "port": cfg.get("port", 18789),
        "url": _get_canvas_url(cfg),
    }


async def auto_start_if_configured(cfg: dict) -> None:
    """Called during app startup: start gateway if auto_start is enabled."""
    if not cfg.get("enabled", False):
        return
    if not cfg.get("auto_start", False):
        return
    if is_running(cfg):
        logger.info("OpenClaw Gateway is already running.")
        return
    logger.info("Auto-starting OpenClaw Gateway…")
    result = await asyncio.get_running_loop().run_in_executor(None, start_gateway, cfg)
    if result["success"]:
        logger.info("OpenClaw Gateway started: %s", result["message"])
    else:
        logger.warning("Failed to auto-start OpenClaw Gateway: %s", result["message"])
