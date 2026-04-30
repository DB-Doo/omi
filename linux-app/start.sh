#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Run from inside linux-app so local imports (auth, daemon, etc.) resolve without a package name
cd "$SCRIPT_DIR"

VENV="$SCRIPT_DIR/venv"

# ── Bootstrap venv on first run ────────────────────────────────────────────────
if [ ! -f "$VENV/bin/activate" ]; then
    echo "[omi] Creating virtual environment…"
    python3 -m venv "$VENV"
    source "$VENV/bin/activate"
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
else
    source "$VENV/bin/activate"
fi

# ── First-time auth check ───────────────────────────────────────────────────────
CONFIG="$HOME/.config/omi-linux/config.json"
if [ ! -f "$CONFIG" ]; then
    echo "[omi] First run — opening browser for Omi login…"
    python3 auth.py login
fi

# ── Start capture daemon in background ─────────────────────────────────────────
python3 daemon.py &
DAEMON_PID=$!
echo "[omi] Daemon started (pid $DAEMON_PID)"

# ── System tray (blocks until quit) ────────────────────────────────────────────
python3 tray.py

# ── Cleanup ────────────────────────────────────────────────────────────────────
kill "$DAEMON_PID" 2>/dev/null || true
