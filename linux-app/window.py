"""Desktop window: serves ui.html via local FastAPI and opens via webview."""

import json
import threading
from pathlib import Path

import uvicorn
import webview
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import daemon as _daemon
from config import UI_PORT

_app = FastAPI()
_UI_HTML = Path(__file__).parent / "ui.html"


@_app.get("/", response_class=HTMLResponse)
def serve_ui():
    return _UI_HTML.read_text()


@_app.get("/api/state")
def api_state():
    recent = _daemon.get_recent_captures(20)
    return JSONResponse({
        "running": _daemon.capture_state["running"],
        "paused": _daemon.capture_state["paused"],
        "last_sync": _daemon.capture_state["last_sync"],
        "last_capture": _daemon.capture_state["last_capture"],
        "count": _daemon.capture_state["count"],
        "recent": recent,
    })


@_app.post("/api/pause")
def api_pause():
    _daemon.capture_state["paused"] = not _daemon.capture_state["paused"]
    return JSONResponse({"paused": _daemon.capture_state["paused"]})


def _start_server():
    uvicorn.run(_app, host="127.0.0.1", port=UI_PORT, log_level="error")


def open_window():
    """Start FastAPI server (once) and open a webview window."""
    server_thread = threading.Thread(target=_start_server, daemon=True)
    server_thread.start()

    import time
    time.sleep(0.5)  # give uvicorn a moment to bind

    webview.create_window(
        "Omi Linux",
        url=f"http://127.0.0.1:{UI_PORT}/",
        width=420,
        height=680,
        resizable=True,
    )
    webview.start(gui="qt")


if __name__ == "__main__":
    open_window()
