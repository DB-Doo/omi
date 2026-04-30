"""Firebase OAuth flow via Omi backend + local token refresh."""

import json
import sys
import time
import socket
import threading
import webbrowser
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

import requests

from config import FIREBASE_API_KEY, OMI_BASE, CONFIG_DIR, CONFIG_FILE


def _find_free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _CallbackHandler(BaseHTTPRequestHandler):
    code = None
    event = threading.Event()

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            _CallbackHandler.code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h2>Omi login complete. You can close this tab.</h2></body></html>"
            )
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Auth failed - no code returned.</h2></body></html>")
        _CallbackHandler.event.set()

    def log_message(self, *args):
        pass  # suppress httpd logs


def login():
    """Open browser, complete Google OAuth via Omi backend, store refresh token."""
    port = _find_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    params = urlencode({"provider": "google", "redirect_uri": redirect_uri})
    auth_url = f"{OMI_BASE}/v1/auth/authorize?{params}"

    _CallbackHandler.code = None
    _CallbackHandler.event.clear()

    server = HTTPServer(("127.0.0.1", port), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print(f"Opening browser for Omi login...")
    webbrowser.open(auth_url)

    if not _CallbackHandler.event.wait(timeout=120):
        server.shutdown()
        raise TimeoutError("Login timed out after 120 seconds")

    server.shutdown()
    code = _CallbackHandler.code
    if not code:
        raise RuntimeError("No auth code received from browser callback")

    # Exchange code for custom Firebase token via Omi backend
    resp = requests.post(
        f"{OMI_BASE}/v1/auth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "use_custom_token": "true",
        },
    )
    resp.raise_for_status()
    token_data = resp.json()
    custom_token = token_data.get("custom_token")
    if not custom_token:
        raise RuntimeError(f"No custom_token in response: {list(token_data.keys())}")

    # Sign in with Firebase custom token (server-generated, works with any API key)
    signin_resp = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={FIREBASE_API_KEY}",
        json={"token": custom_token, "returnSecureToken": True},
    )
    if not signin_resp.ok:
        print(f"[debug] signInWithCustomToken {signin_resp.status_code}: {signin_resp.text[:400]}")
    signin_resp.raise_for_status()
    signin_data = signin_resp.json()

    id_token = signin_data["idToken"]
    refresh_token = signin_data["refreshToken"]
    uid = signin_data["localId"]

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config = {
        "firebase_refresh_token": refresh_token,
        "firebase_uid": uid,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    print(f"Login successful. UID: {uid}")
    return id_token, refresh_token, uid


def refresh_token(stored_refresh_token: str) -> tuple[str, str]:
    """Exchange refresh token for fresh idToken. Returns (id_token, new_refresh_token)."""
    resp = requests.post(
        f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}",
        data={"grant_type": "refresh_token", "refresh_token": stored_refresh_token},
    )
    resp.raise_for_status()
    data = resp.json()
    return data["id_token"], data.get("refresh_token", stored_refresh_token)


def load_config() -> dict | None:
    """Return stored config or None if not logged in."""
    if not CONFIG_FILE.exists():
        return None
    return json.loads(CONFIG_FILE.read_text())


def save_config(config: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


class TokenManager:
    """Thread-safe Firebase token manager with auto-refresh."""

    def __init__(self, refresh_tok: str):
        self._refresh_tok = refresh_tok
        self._id_tok: str | None = None
        self._expires_at: float = 0
        self._lock = threading.Lock()

    def get_token(self) -> str | None:
        with self._lock:
            if time.time() >= self._expires_at:
                try:
                    self._id_tok, self._refresh_tok = refresh_token(self._refresh_tok)
                    self._expires_at = time.time() + 55 * 60
                    cfg = load_config() or {}
                    cfg["firebase_refresh_token"] = self._refresh_tok
                    save_config(cfg)
                except Exception as e:
                    print(f"[auth] Token refresh failed: {e}")
                    return None
            return self._id_tok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login()
    else:
        print("Usage: python3 auth.py login")
