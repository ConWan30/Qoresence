"""Mobile glass — FrameHub view page + honest LAN link."""

from __future__ import annotations

from qoresence.deck import webrtc_hub
from qoresence.deck.server import _html, create_app, glass_link_info


def test_webrtc_stats_still_frame_hub():
    s = webrtc_hub.stats()
    assert s.get("source") == "frame_hub"
    assert "available" in s


def test_mobile_page_is_glass_not_capture():
    html = _html("mobile.html")
    assert "playsinline" in html
    assert "autoplay" in html
    assert "muted" in html
    assert "/api/webrtc/status" in html
    assert "/api/webrtc/offer" in html
    assert "/video" in html
    assert "FrameHub glass" in html
    assert "no second capture" in html
    assert "max_width:960" in html or "max_width: 960" in html


def test_glass_link_localhost_is_not_lan():
    info = glass_link_info("127.0.0.1", 8765)
    assert info["lan"] is False
    assert info["url"] == "http://127.0.0.1:8765/mobile.html"
    assert "LAN bind" in info["note"] or "localhost" in info["note"].lower()


def test_glass_link_wildcard_is_opt_in_lan():
    info = glass_link_info("0.0.0.0", 8765)
    assert info["lan"] is True
    assert info["path"] == "/mobile.html"
    assert "8765/mobile.html" in info["url"]


def test_mobile_routes_registered():
    app = create_app()
    if app is None:
        return
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/mobile.html" in paths
    assert "/glass" in paths
    assert "/api/glass-link" in paths
    assert "/api/webrtc/status" in paths
    assert "/api/webrtc/offer" in paths
    deck = _html("deck.html")
    assert "btnGlassCopy" in deck
    assert "/mobile.html" in deck
