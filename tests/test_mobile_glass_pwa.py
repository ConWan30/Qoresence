"""Mobile Glass PWA + mDNS auto-discovery — phase 2 native glass shell.

Covers:
- ``qoresence.deck.mdns`` broadcaster (loopback no-op, discovery_info shape)
- deck routes: ``/api/discover``, ``/manifest.webmanifest``, ``/sw.js``,
  ``/icons/{name}`` (registered + path-traversal guarded)
- PWA static assets: manifest is valid JSON with the 4 declared icons, sw.js
  is a service worker, icon PNGs exist on disk and are packaged
- ``mobile.html`` pairing gate: when served from the deck (http(s) + host) the
  gate is skipped so a localhost viewer never sees "No Qoresence found"
- security: mDNS never advertises on loopback; discovery_info stays honest
"""

from __future__ import annotations

import json
import pathlib

import pytest

from qoresence.deck import mdns
from qoresence.deck.server import _html, create_app

_DECK = pathlib.Path(__file__).resolve().parents[1] / "qoresence" / "deck"


# --- mdns module ---------------------------------------------------------


def test_mdns_loopback_bind_is_detected():
    assert mdns.is_loopback_bind("127.0.0.1")
    assert mdns.is_loopback_bind("localhost")
    assert mdns.is_loopback_bind("::1")
    assert mdns.is_loopback_bind("")
    assert mdns.is_loopback_bind(None)
    assert not mdns.is_loopback_bind("0.0.0.0")
    assert not mdns.is_loopback_bind("192.168.1.10")


def test_start_mdns_is_noop_on_loopback():
    """Loopback bind must never advertise on the LAN (release gate)."""
    assert mdns.start_mdns(8765, "127.0.0.1") is False
    assert mdns.start_mdns(8765, "localhost") is False
    assert mdns.start_mdns(8765, None) is False
    # nothing registered
    assert mdns._runtime is None


def test_discovery_info_loopback_is_honest():
    info = mdns.discovery_info(8765, "127.0.0.1")
    assert info["lan"] is False
    assert info["host"] is None
    assert info["url"] is None
    assert info["advertising"] is False
    assert info["port"] == 8765
    assert info["path"] == "/mobile.html"
    assert info["service"] == "_qoresence._tcp.local."


def test_discovery_info_includes_service_type_for_native_scan():
    """The native NSD plugin scans for _qoresence._tcp — keep the type stable."""
    info = mdns.discovery_info(8765, "127.0.0.1")
    assert "_qoresence._tcp" in info["service"]


def test_stop_mdns_is_safe_when_never_started():
    # Should not raise even when nothing was advertising.
    mdns.stop_mdns()


# --- deck routes ---------------------------------------------------------


@pytest.fixture
def app():
    a = create_app()
    if a is None:
        pytest.skip("fastapi not installed")
    return a


def test_pwa_routes_registered(app):
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/api/discover" in paths
    assert "/manifest.webmanifest" in paths
    assert "/sw.js" in paths
    assert "/icons/{name}" in paths
    assert "/live.jpg" in paths


def test_discover_route_calls_mdns_discovery_info(app, monkeypatch):
    """The /api/discover handler must delegate to mdns.discovery_info and
    echo its lan/host/url fields — never invent a LAN address on loopback."""
    captured: dict = {}

    def fake_discovery_info(port, host=None):
        captured["port"] = port
        captured["host"] = host
        return {
            "service": "_qoresence._tcp.local.",
            "name": None,
            "host": None,
            "port": port,
            "path": "/mobile.html",
            "url": None,
            "lan": False,
            "advertising": False,
        }

    # The route does `from qoresence.deck.mdns import discovery_info` inside
    # the handler, so patching the mdns module attribute is enough.
    monkeypatch.setattr(mdns, "discovery_info", fake_discovery_info)

    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")

    client = TestClient(app)
    body = client.get("/api/discover").json()
    assert body["ok"] is True
    assert body["lan"] is False
    assert body["url"] is None
    assert captured["port"] is not None


# --- static assets -------------------------------------------------------


def test_manifest_is_valid_json_with_four_icons():
    raw = (_DECK / "manifest.webmanifest").read_text(encoding="utf-8")
    m = json.loads(raw)
    assert m["name"] == "Qoresence Glass"
    assert m["start_url"] == "/mobile.html"
    assert m["display"] == "standalone"
    assert m["theme_color"] == "#05080a"
    icons = m["icons"]
    assert len(icons) == 4
    sizes = {i["sizes"] for i in icons}
    assert {"192x192", "512x512"} <= sizes
    purposes = {i["purpose"] for i in icons}
    assert "any" in purposes and "maskable" in purposes
    # every declared icon file exists on disk
    for i in icons:
        name = pathlib.PurePosixPath(i["src"]).name
        assert (_DECK / "icons" / name).is_file(), f"missing icon {name}"


def test_service_worker_is_a_real_sw():
    sw = (_DECK / "sw.js").read_text(encoding="utf-8")
    assert "serviceWorker" not in sw  # it IS the sw, doesn't register itself
    assert "addEventListener('install'" in sw or 'addEventListener("install"' in sw
    assert "addEventListener('fetch'" in sw or 'addEventListener("fetch"' in sw
    # live data must never be cached
    assert "/video" in sw and "/api/" in sw
    assert "/live.jpg" in sw
    assert "qoresence-glass-v1" in sw


def test_icon_pngs_are_packaged_and_nonempty():
    icons = sorted((_DECK / "icons").glob("*.png"))
    names = {p.name for p in icons}
    assert {
        "glass-192.png",
        "glass-512.png",
        "glass-192-maskable.png",
        "glass-512-maskable.png",
    } <= names
    for p in icons:
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{p.name} is not a PNG"


def test_package_data_includes_pwa_assets():
    """pyproject must package the manifest, sw, and icons so installed runs
    serve them (not just source checkouts)."""
    pp = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"
    txt = pp.read_text(encoding="utf-8")
    assert "deck/*.webmanifest" in txt
    assert "deck/*.js" in txt
    assert "deck/icons/*.png" in txt


# --- mobile.html pairing gate -------------------------------------------


def test_mobile_html_skips_pairing_when_served_from_deck():
    """The PWA is served BY the deck with relative live URLs, so the pairing
    screen must not gate a viewer who is already on the deck (regression:
    previously showed 'No Qoresence found' on localhost first run)."""
    html = _html("mobile.html")
    assert "servedFromDeck" in html
    assert "location.protocol" in html
    # The pairing overlay element still exists (used by bundled/native shell).
    assert 'id="pair"' in html
    # PWA manifest + sw + apple touch icon are wired in <head>
    assert "/manifest.webmanifest" in html
    assert "/sw.js" in html
    assert "/icons/glass-192.png" in html


def test_mobile_html_uses_relative_live_urls():
    """All live data URLs in the deck-served PWA are relative — never absolute
    to a stored host. The stored host is only for the native bundled shell."""
    html = _html("mobile.html")
    assert "fetch('/api/situation')" in html or 'fetch("/api/situation")' in html
    assert "fetch('/api/webrtc/status')" in html or 'fetch("/api/webrtc/status")' in html
    assert "mjpeg.src='/video" in html or 'mjpeg.src="/video' in html
    # Must not build an absolute hostUrl for live data in the PWA.
    assert "hostUrl + '/api/situation'" not in html


# --- icon route path-traversal guard ------------------------------------


def test_icon_route_rejects_traversal(app):
    """The /icons/{name} allowlist must refuse .., slashes, and non-png."""
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(app)
    for bad in [
        "/icons/..%2F..%2Fserver.py",
        "/icons/glass-192.png/..",
        "/icons/glass-192.jpg",  # wrong ext
        "/icons/../server.py",
    ]:
        r = client.get(bad)
        assert r.status_code in (404, 400), f"{bad} should be rejected, got {r.status_code}"
    # a valid icon serves
    r = client.get("/icons/glass-192.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_situation_payload_exposes_coupling_without_inventing_score():
    """Native Glass polls /api/situation for clutch. Coupling must be present
    even with no IVC; digits stay fail-closed (no invented home/away)."""
    from qoresence.deck.server import _situation_payload

    snap = _situation_payload()
    assert "coupling" in snap
    assert "phrase" in snap["coupling"]
    assert "climax_score" in snap["coupling"]
    sit = snap.get("situation") or {}
    locked = bool(
        sit.get("score_vlm_locked") or sit.get("scoreboard_locked") or sit.get("title_claim")
    )
    if not locked:
        # Unlocked board must not present a painted score to the glass.
        assert sit.get("home_score") is None or sit.get("home_score") == 0
        assert sit.get("away_score") is None or sit.get("away_score") == 0


def test_native_shell_is_cinema_not_mjpeg():
    """Android WebView cannot play MJPEG. The bundled shell pumps /live.jpg."""
    html = (
        pathlib.Path(__file__).resolve().parents[1] / "native" / "www" / "index.html"
    ).read_text(encoding="utf-8")
    assert "/live.jpg" in html
    assert "QoreCinema" in html
    assert "enterPip" in html
    assert "pipChanged" in html
    assert "document.hidden && !inPip" in html
    assert "POST" in html and "/api/clip" in html
    assert "score_vlm_locked" in html
    assert "multipart/x-mixed-replace" not in html
    assert "mjpeg.src" not in html


def test_live_jpeg_is_503_until_hdmi_frame(app):
    """Cinema pump must not treat the MJPEG placeholder as a live still."""
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")
    from qoresence.deck import server as deck_server
    from qoresence.vision.clip_buffer import get_clip_buffer

    # Ensure a previous test's clip buffer state doesn't leak into this hermetic test.
    buf = get_clip_buffer()
    buf._live_jpeg = None
    buf._live_seq = 0
    buf._frames.clear()
    assert deck_server._read_live_jpeg() == b""
    client = TestClient(app)
    r = client.get("/live.jpg")
    assert r.status_code == 503
    r = client.get("/api/situation")
    assert r.status_code == 200
    assert "coupling" in r.json()


def test_live_jpeg_serves_hdmi_bytes(app, monkeypatch):
    """When ClipBuffer has a still, /live.jpg is that JPEG — no second capture."""
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")
    from qoresence.deck import server as deck_server

    fake = b"\xff\xd8fake-hdmi-jpeg\xff\xd9"
    monkeypatch.setattr(deck_server, "_read_live_jpeg", lambda: fake)
    client = TestClient(app)
    r = client.get("/live.jpg")
    assert r.status_code == 200
    assert r.content == fake
    assert r.headers["content-type"] == "image/jpeg"
    assert "no-store" in r.headers.get("cache-control", "")


def test_native_sw_never_caches_live_jpeg():
    sw = (
        pathlib.Path(__file__).resolve().parents[1] / "native" / "www" / "sw.js"
    ).read_text(encoding="utf-8")
    assert "/live.jpg" in sw
    assert "/video" in sw
    assert "/api/" in sw
