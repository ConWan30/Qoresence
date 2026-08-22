"""Mobile glass — FrameHub view page + honest LAN link."""

from __future__ import annotations

from qoresence.deck import webrtc_hub
from qoresence.deck.server import _html, create_app, glass_link_info


def test_theater_shows_hdmi_age_not_just_vlm():
    html = _html("deck.html")
    if 'id="root"' in html or "id='root'" in html:
        from pathlib import Path

        assets = Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "glass_spa" / "assets"
        js = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in assets.glob("*.js"))
        assert "videoAgeS" in js or "videoAge" in js
        return
    assert "hdmi " in html and "ms" in html
    assert "snap.video.age_s" in html or "snap.video && snap.video.age_s" in html


def test_webrtc_stats_still_frame_hub():
    s = webrtc_hub.stats()
    assert s.get("source") == "frame_hub"
    assert "available" in s


def test_mobile_page_is_glass_not_capture():
    html = _html("mobile.html")
    # SPA ship (#25): mobile.html is the Retina Deck glass index, not the old
    # FrameHub capture page. Prefer #root + assets; keep legacy asserts only
    # when the packaged SPA is absent.
    if 'id="root"' in html or "id='root'" in html:
        assert "Retina Deck" in html or "/assets/" in html
        assert "capture" not in html.lower() or "no second capture" in html.lower()
        return
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


def test_glass_qr_has_finder_patterns():
    from qoresence.deck.glass_qr import encode_modules

    m = encode_modules("http://192.168.1.20:8765/mobile.html")
    n = len(m)
    assert n >= 21
    # Finder corners are dark
    assert m[0][0] == 1 and m[0][6] == 1 and m[6][0] == 1 and m[6][6] == 1
    assert m[2][2] == 1 and m[3][3] == 1
    assert m[0][n - 1] == 1 and m[6][n - 1] == 1
    assert m[n - 1][0] == 1 and m[n - 1][6] == 1


def test_glass_qr_svg_from_url():
    from qoresence.deck.glass_qr import url_to_svg

    svg = url_to_svg("http://10.0.0.4:8765/mobile.html")
    assert svg.startswith("<svg")
    assert "rect" in svg


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
    assert "/live.jpg" in paths
    assert "/glass.apk" in paths
    deck = _html("deck.html")
    assert "btnGlassCopy" in deck
    assert "/mobile.html" in deck
