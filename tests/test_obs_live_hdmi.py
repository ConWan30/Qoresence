"""Pattern B HDMI glass — /obs-live.html served for OBS CEF (not raw /video)."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "qoresence" / "deck"
OBS_LIVE = DECK / "obs-live.html"


def test_obs_live_html_ships_brand_and_mjpeg_embed():
    assert OBS_LIVE.is_file(), "qoresence/deck/obs-live.html missing"
    body = OBS_LIVE.read_text(encoding="utf-8")
    assert "object-fit:cover" in body.replace(" ", "") or "object-fit: cover" in body
    assert "/video?fps=30" in body or "FPS = 30" in body or "fps=' + FPS" in body
    html = OBS_LIVE.read_text(encoding="utf-8")
    assert "QORESENCE" in html
    assert "HDMI PORT" in html
    assert "USB3.0 VIDEO" in html
    assert "PATTERN B" in html
    assert "/video?fps=" in html or "fps=" in html
    assert 'id="feed"' in html
    # Must not be a transparent lens-only page (pixels need opaque stage + brand).
    assert "background:#05060A" in html or "background:#000" in html


def test_obs_live_not_in_glass_spa_names():
    from qoresence.deck.server import _GLASS_HTML_NAMES, _html

    assert "obs-live.html" not in _GLASS_HTML_NAMES
    body = _html("obs-live.html")
    assert "QORESENCE" in body
    assert 'id="root"' not in body  # never glass SPA shell


def test_obs_live_routes_registered_in_server_source():
    """FastAPI + stdlib paths both register /obs-live.html (no live bind needed)."""
    src = (DECK / "server.py").read_text(encoding="utf-8")
    assert '@app.get("/obs-live.html")' in src
    assert "async def obs_live(" in src
    assert '_html("obs-live.html")' in src
    assert 'self.path == "/obs-live.html"' in src
    assert "HDMI /obs-live.html" in src


def test_obs_live_http_smoke():
    pytest.importorskip("fastapi")
    from qoresence.deck import server as deck

    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")

    app = deck.create_app()
    client = TestClient(app)
    r = client.get("/obs-live.html")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    assert "QORESENCE" in body
    assert "PATTERN B" in body
    assert "/video" in body
    assert 'id="root"' not in body


def test_pattern_b_helper_script_exists():
    ps1 = ROOT / "tools" / "obs" / "pattern_b_x_live.ps1"
    assert ps1.is_file()
    text = ps1.read_text(encoding="utf-8")
    assert "obs-live.html" in text
    assert "SafeMode=false" in text
    assert "--startstreaming" in text
    assert "OBS_NORMAL_MODE" in text or "OBS_SAFE_OR_NORMAL" in text
    assert "STREAM_MARK_OK" in text
    assert "service.json" in text  # mentioned only as a forbidden print surface
    assert "sk_live" not in text
    assert "stream_key=" not in text.replace(" ", "")
