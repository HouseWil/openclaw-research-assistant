#!/usr/bin/env bash
# ============================================================
# OpenClaw Research Assistant - Start Script (Linux / macOS)
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ___                  ____ _"
echo " / _ \\ _ __   ___ _ __/ ___| | __ ___      __"
echo "| | | | '_ \\ / _ \\ '_ \\___ \\ |/ _\` \\ \\ /\\ / /"
echo "| |_| | |_) |  __/ | | |__) | | (_| |\\ V  V /"
echo " \\___/| .__/ \\___|_| |_|____/|_|\\__,_| \\_/\\_/"
echo "      |_|   科研助手 v1.0.0"
echo ""

# ── Check Python ──────────────────────────────────────────
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "❌  Python 未找到，请先安装 Python 3.9+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# ── Check Python version ──────────────────────────────────
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$("$PYTHON" -c "import sys; print(sys.version_info.major)")
PY_MINOR=$("$PYTHON" -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    echo "❌  需要 Python 3.9+，当前版本: $PY_VERSION"
    exit 1
fi
echo "✅  Python $PY_VERSION"

# ── Install/check dependencies ───────────────────────────
if ! "$PYTHON" -c "import fastapi" &>/dev/null 2>&1; then
    echo "📦  正在安装依赖包..."
    "$PYTHON" -m pip install -r requirements.txt -q
    echo "✅  依赖安装完成"
else
    echo "✅  依赖已就绪"
fi

# ── Launch ────────────────────────────────────────────────
echo ""
"$PYTHON" install.py "$@"
