#!/usr/bin/env bash
# Start the SWMS web dashboard bridge
# Usage:  ./start.sh [port]
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-8000}"
VENV="$SCRIPT_DIR/.venv"

cd "$SCRIPT_DIR"

# Bootstrap venv if missing or stale (e.g. after folder rename)
if ! "$VENV/bin/python3" -c "import uvicorn" 2>/dev/null; then
    echo "[dashboard] Installing dependencies into .venv ..."
    python3 -m venv --clear "$VENV"
    "$VENV/bin/pip" install -q -r requirements.txt
fi

echo "[dashboard] Starting bridge on http://0.0.0.0:${PORT}"
exec "$VENV/bin/python3" -m uvicorn bridge:app --host 0.0.0.0 --port "$PORT" --reload
