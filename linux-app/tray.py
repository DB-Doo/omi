"""System tray icon for Omi Linux."""

import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

import daemon as _daemon


def _make_icon(paused: bool = False) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = "#888888" if paused else "#FF6B35"
    draw.ellipse([8, 8, 56, 56], fill=color)
    return img


def _open_window():
    """Launch the desktop window in a background thread."""
    import window
    t = threading.Thread(target=window.open_window, daemon=True)
    t.start()


def _toggle_pause(icon: pystray.Icon, item):
    _daemon.capture_state["paused"] = not _daemon.capture_state["paused"]
    paused = _daemon.capture_state["paused"]
    icon.icon = _make_icon(paused)
    icon.title = "Omi Linux (paused)" if paused else "Omi Linux"
    # Rebuild menu to update label
    icon.menu = _build_menu(icon)


def _quit_app(icon: pystray.Icon, item):
    _daemon.capture_state["running"] = False
    icon.stop()


def _build_menu(icon: pystray.Icon) -> pystray.Menu:
    paused = _daemon.capture_state["paused"]
    pause_label = "Resume capture" if paused else "Pause capture"
    return pystray.Menu(
        pystray.MenuItem("Open Omi", lambda: _open_window()),
        pystray.MenuItem(pause_label, lambda i, it: _toggle_pause(i, it)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", _quit_app),
    )


def run_tray():
    icon = pystray.Icon(
        "Omi Linux",
        _make_icon(False),
        "Omi Linux",
    )
    icon.menu = _build_menu(icon)
    icon.run()


if __name__ == "__main__":
    run_tray()
