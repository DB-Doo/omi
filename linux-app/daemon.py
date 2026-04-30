"""Screen capture daemon: screenshot → OCR → SQLite → cloud sync."""

import io
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytesseract
import requests
from PIL import Image

from auth import TokenManager, load_config
from config import (
    CAPTURE_INTERVAL,
    DB_FILE,
    RUST_BACKEND,
    SYNC_BATCH_SIZE,
)

# Shared state for tray/window to read
capture_state = {
    "running": True,
    "paused": False,
    "last_sync": None,
    "last_capture": None,
    "count": 0,
}


def _init_db():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS captures (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            ts       TEXT NOT NULL,
            app_name TEXT,
            win_title TEXT,
            ocr_text TEXT,
            synced   INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def _screenshot() -> Image.Image | None:
    try:
        result = subprocess.run(
            ["scrot", "-z", "-"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return Image.open(io.BytesIO(result.stdout))
    except Exception as e:
        print(f"[daemon] Screenshot failed: {e}")
        return None


def _get_active_window() -> tuple[str, str]:
    try:
        win_id = subprocess.check_output(
            ["xdotool", "getactivewindow"], timeout=5
        ).decode().strip()
        win_name = subprocess.check_output(
            ["xdotool", "getwindowname", win_id], timeout=5
        ).decode().strip()
        # Get WM_CLASS for the app name via xprop
        try:
            xprop_out = subprocess.check_output(
                ["xprop", "-id", win_id, "WM_CLASS"], timeout=5
            ).decode()
            # WM_CLASS = "name", "ClassName"
            parts = xprop_out.split('"')
            class_out = parts[-2] if len(parts) >= 2 else "Unknown"
        except Exception:
            class_out = "Unknown"
        return class_out or "Unknown", win_name or ""
    except Exception:
        return "Unknown", ""


def _ocr(img: Image.Image) -> str:
    try:
        text = pytesseract.image_to_string(img)
        return text.strip()[:1000]
    except Exception as e:
        print(f"[daemon] OCR failed: {e}")
        return ""


def _sync_batch(conn: sqlite3.Connection, token_mgr: TokenManager | None):
    """Pull unsynced rows from DB and POST to cloud. Tolerates auth failure."""
    rows = conn.execute(
        "SELECT id, ts, app_name, win_title, ocr_text FROM captures WHERE synced=0 ORDER BY id LIMIT ?",
        (SYNC_BATCH_SIZE,),
    ).fetchall()

    if not rows:
        return

    payload_rows = [
        {
            "id": r[0],
            "timestamp": r[1],
            "appName": r[2] or "",
            "windowTitle": r[3] or "",
            "ocrText": r[4] or "",
            "embedding": None,
        }
        for r in rows
    ]

    synced = False
    if token_mgr:
        id_tok = token_mgr.get_token()
        if id_tok:
            try:
                resp = requests.post(
                    f"{RUST_BACKEND}/v1/screen-activity/sync",
                    json={"rows": payload_rows},
                    headers={"Authorization": f"Bearer {id_tok}"},
                    timeout=15,
                )
                resp.raise_for_status()
                synced = True
                capture_state["last_sync"] = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                print(f"[daemon] Cloud sync failed: {e}")

    if synced:
        ids = tuple(r[0] for r in rows)
        conn.execute(
            f"UPDATE captures SET synced=1 WHERE id IN ({','.join('?' * len(ids))})", ids
        )
        conn.commit()


def capture_loop(token_mgr: TokenManager | None = None):
    conn = _init_db()
    pending_since_sync = 0

    while capture_state["running"]:
        if capture_state["paused"]:
            time.sleep(5)
            continue

        img = _screenshot()
        if img is None:
            time.sleep(CAPTURE_INTERVAL)
            continue

        ocr_text = _ocr(img)
        app_name, win_title = _get_active_window()
        ts = datetime.now(timezone.utc).isoformat()

        conn.execute(
            "INSERT INTO captures (ts, app_name, win_title, ocr_text) VALUES (?, ?, ?, ?)",
            (ts, app_name, win_title, ocr_text),
        )
        conn.commit()

        capture_state["last_capture"] = {
            "ts": ts,
            "app_name": app_name,
            "win_title": win_title,
            "ocr_text": ocr_text[:200],
        }
        capture_state["count"] += 1
        pending_since_sync += 1

        if pending_since_sync >= SYNC_BATCH_SIZE:
            _sync_batch(conn, token_mgr)
            pending_since_sync = 0

        time.sleep(CAPTURE_INTERVAL)

    conn.close()


def get_recent_captures(n: int = 20) -> list[dict]:
    """Read last n captures from SQLite (for window UI)."""
    if not DB_FILE.exists():
        return []
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT ts, app_name, win_title, ocr_text FROM captures ORDER BY id DESC LIMIT ?", (n,)
    ).fetchall()
    conn.close()
    return [{"ts": r[0], "app": r[1], "title": r[2], "text": r[3]} for r in rows]


if __name__ == "__main__":
    cfg = load_config()
    mgr = TokenManager(cfg["firebase_refresh_token"]) if cfg else None
    capture_loop(mgr)
