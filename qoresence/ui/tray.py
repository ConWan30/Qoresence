"""System tray status indicator for Qoresence.

Shows a tray icon with live status (UP/DOWN/score) and quick actions:
  - Open Deck (browser)
  - Health check
  - Stop server
  - Quit tray (server keeps running)

Requires pystray + Pillow (both pip-installable).
Default OFF — enabled with --tray.
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

log = logging.getLogger(__name__)

_TRAY: Any | None = None
_TRAY_THREAD: threading.Thread | None = None


def _fetch_health(port: int = 8765, timeout: float = 2.0) -> dict[str, Any] | None:
    try:
        import json

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _make_icon_image(status: str = "idle") -> Any:
    """Generate a simple colored circle icon."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colors = {
        "up": (46, 204, 113, 255),  # green
        "down": (231, 76, 60, 255),  # red
        "idle": (245, 197, 66, 255),  # gold
        "warn": (243, 156, 18, 255),  # orange
    }
    color = colors.get(status, colors["idle"])
    draw.ellipse((8, 8, 56, 56), fill=color)
    draw.ellipse((8, 8, 56, 56), outline=(255, 255, 255, 80), width=2)
    # Letter Q
    draw.text((22, 16), "Q", fill=(10, 14, 20, 255))
    return img


def _format_tooltip(h: dict[str, Any] | None) -> tuple[str, str]:
    """Return (status, tooltip_text) from health response."""
    if h is None:
        return "down", "Qoresence — server down"
    sit = (h.get("state") or {}).get("situation") or {}
    score = sit.get("home_score")
    if score is not None:
        sc = f"{sit.get('home_score')}-{sit.get('away_score')} Q{sit.get('quarter') or '?'}"
    else:
        sc = "warming…"
    sync = "sync" if sit.get("presence_sync_ok") else "no pad"
    return "up", f"Qoresence — {sc} · {sync}"


def _open_deck(port: int = 8765) -> None:
    try:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/deck.html")
    except Exception as e:
        log.debug("open deck failed: %s", e)


def start_tray(
    *,
    port: int = 8765,
    poll_interval_s: float = 5.0,
    on_stop: Any | None = None,
) -> tuple[threading.Thread, threading.Event]:
    """Start the system tray icon on a daemon thread.

    Returns (thread, stop_event). The tray polls /health every poll_interval_s
    and updates the icon color + tooltip.
    """
    import pystray

    stop = threading.Event()
    state = {"status": "idle", "tooltip": "Qoresence — starting…"}

    def _on_open(icon, item):
        _open_deck(port)

    def _on_quit(icon, item):
        stop.set()
        icon.stop()

    def _on_stop(icon, item):
        if on_stop:
            try:
                on_stop()
            except Exception:
                pass
        stop.set()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open Deck", _on_open, default=True),
        pystray.MenuItem("Stop server", _on_stop),
        pystray.MenuItem("Quit tray", _on_quit),
    )

    icon = pystray.Icon(
        "qoresence",
        _make_icon_image("idle"),
        state["tooltip"],
        menu,
    )

    def _poll() -> None:
        while not stop.is_set():
            h = _fetch_health(port)
            status, tooltip = _format_tooltip(h)
            state["status"] = status
            state["tooltip"] = tooltip
            try:
                icon.icon = _make_icon_image(status)
                icon.title = tooltip
            except Exception:
                pass
            stop.wait(poll_interval_s)

    poll_t = threading.Thread(target=_poll, name="qoresence-tray-poll", daemon=True)
    poll_t.start()

    def _run() -> None:
        try:
            log.info("Qoresence tray icon started (port=%s)", port)
            icon.run()
        except Exception as e:
            log.debug("tray stopped: %s", e)

    t = threading.Thread(target=_run, name="qoresence-tray", daemon=True)
    t.start()
    return t, stop


def stop_tray() -> None:
    """Stop the tray icon if running."""
    global _TRAY
    if _TRAY is not None:
        try:
            _TRAY.stop()
        except Exception:
            pass
        _TRAY = None
