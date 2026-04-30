import os
from pathlib import Path

FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")
OMI_BASE = "https://api.omi.me"
RUST_BACKEND = "https://desktop-backend-dt5lrfkkoa-uc.a.run.app"

CAPTURE_INTERVAL = 30  # seconds between screenshots
SYNC_BATCH_SIZE = 5    # captures per cloud sync
TOKEN_REFRESH_INTERVAL = 55 * 60  # seconds (55 min)

UI_PORT = 8766
CONFIG_DIR = Path.home() / ".config" / "omi-linux"
CONFIG_FILE = CONFIG_DIR / "config.json"
DB_FILE = CONFIG_DIR / "activity.db"
