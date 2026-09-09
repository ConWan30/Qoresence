"""DeckLeaseLamp — subscribe-not-own chrome. Default OFF. No digits. No dual-open."""

from __future__ import annotations

from pathlib import Path

import pytest

from qoresence.core.unified_config import RetinaUnifiedConfig
from qoresence.deck.lease_lamp import (
    ENV_NAME,
    FLAG_NAME,
    PLANE,
    attach_health,
    enabled,
    reset,
    set_config_enabled,
    snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
LAMP_PY = ROOT / "qoresence" / "deck" / "lease_lamp.py"
LAMP_JS = ROOT / "qoresence" / "deck" / "lease_lamp.js"
DECK_HTML = ROOT / "qoresence" / "deck" / "deck.html"
CLI = ROOT / "qoresence" / "cli.py"

_LAMP_SOURCES = (LAMP_PY, LAMP_JS)


@pytest.fixture(autouse=True)
def _lamp_off(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)
    reset()
    yield
    reset()


def _on(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "1")
    reset()
    monkeypatch.setenv(ENV_NAME, "1")


def test_deck_lease_lamp_default_off():
    assert enabled() is False
    assert snapshot() is None
    assert RetinaUnifiedConfig().deck_lease_lamp is False
    monkeypatch_env_off = RetinaUnifiedConfig.from_env()
    assert monkeypatch_env_off.deck_lease_lamp is False
    body = {"lease": {"ok": True, "owner": "qoresence-streamer", "pid": 1, "device": "USB3.0 Video"}}
    attach_health(body)
    assert "deck_lease_lamp" not in body


def test_play_does_not_enable_lease_lamp():
    assert enabled() is False
    assert RetinaUnifiedConfig().deck_lease_lamp is False
    src = CLI.read_text(encoding="utf-8")
    assert "deck_lease_lamp=True" not in src
    play_idx = src.find('if getattr(args, "play", False):')
    assert play_idx != -1
    play_block = src[play_idx : play_idx + 8000]
    assert "deck_lease_lamp" not in play_block
    assert "lease_lamp" not in play_block
    assert "DeckLeaseLamp stays OFF unless --deck-lease-lamp." in src


def test_lamp_emits_plane_tag(monkeypatch):
    _on(monkeypatch)
    snap = snapshot(
        lease={"ok": True, "owner": "qoresence-streamer", "pid": 9, "device": "USB3.0 Video"},
        hub={"has_frame": True, "age_s": 0.2, "publishes": 14, "seq": 14},
        webrtc={"peers": 0},
    )
    assert snap is not None
    assert snap["plane"] == PLANE
    assert snap["plane"] == "qoresence-observation"
    assert snap["flag"] == FLAG_NAME
    assert snap["lamp"] == "on"
    health: dict = {
        "lease": {"ok": True, "owner": "qoresence-streamer", "pid": 9, "device": "USB3.0 Video"},
        "state": {"video": {"hub_has_frame": True, "hub_age_s": 0.2, "hub_seq": 14, "frames": 14}},
        "webrtc": {"peers": 1, "source": "frame_hub"},
    }
    attach_health(health)
    assert health["deck_lease_lamp"]["plane"] == PLANE
    js = LAMP_JS.read_text(encoding="utf-8")
    html = DECK_HTML.read_text(encoding="utf-8")
    assert 'data-plane' in js
    assert PLANE in js
    assert 'data-plane="qoresence-observation"' in html


def test_lamp_dark_when_lease_not_ok(monkeypatch):
    _on(monkeypatch)
    dark = snapshot(
        lease={"ok": False, "owner": "", "pid": 0, "device": "USB3.0 Video"},
        hub={"has_frame": True, "age_s": 0.1, "publishes": 3, "seq": 3},
    )
    assert dark is not None
    assert dark["lamp"] == "dark"
    assert dark["ok"] is False
    assert dark["lease_ok"] is False
    assert dark["plane"] == PLANE

    missing = snapshot(
        lease={"ok": True, "owner": "qoresence-streamer", "pid": 3, "device": "USB3.0 Video"},
        hub={"has_frame": False, "age_s": None, "publishes": 0, "seq": 0},
        webrtc={"peers": 0},
    )
    assert missing is not None
    assert missing["lamp"] == "dark"
    assert missing["subscribed"] is False
    assert missing["ok"] is False


def test_lamp_source_has_no_digit_paint():
    forbidden = (
        "home_score",
        "away_score",
        "0-0",
        "0–0",
        "0—0",
        "last_good",
        "confirm_ticket",
        "score_vlm",
        "LocalScoreReferee",
        "LocalMuse",
        "wrap_observation",
    )
    for path in _LAMP_SOURCES:
        text = path.read_text(encoding="utf-8")
        for tok in forbidden:
            assert tok not in text, f"{path.name} must not paint {tok}"
        assert "VideoCapture" not in text
        assert "cv2.VideoCapture" not in text
        assert "getUserMedia" not in text
        assert "VideoCapture(" not in text
    html = DECK_HTML.read_text(encoding="utf-8")
    start = html.find("<!-- deck-lease-lamp -->")
    end = html.find("<!-- /deck-lease-lamp -->")
    assert start != -1 and end != -1
    stub = html[start:end]
    for tok in forbidden:
        assert tok not in stub, f"deck.html lamp stub must not paint {tok}"
    py = LAMP_PY.read_text(encoding="utf-8")
    assert "VideoCapture" not in py
    snap = snapshot(
        lease={"ok": True, "owner": "qoresence-streamer", "pid": 1, "device": "USB3.0 Video"},
        hub={"has_frame": True, "age_s": 0.05, "publishes": 8, "seq": 8},
    )
    # Flag still off in this test — emit must be absent, never a painted board.
    assert snap is None
    set_config_enabled(True)
    lit = snapshot(
        lease={"ok": True, "owner": "qoresence-streamer", "pid": 1, "device": "USB3.0 Video"},
        hub={"has_frame": True, "age_s": 0.05, "publishes": 8, "seq": 8},
    )
    assert lit is not None
    allowed = {
        "enabled",
        "plane",
        "lamp",
        "ok",
        "lease_ok",
        "owner",
        "pid",
        "device",
        "subscribed",
        "age_s",
        "frames",
        "flag",
    }
    assert set(lit) == allowed
    assert "home_score" not in lit
    assert "away_score" not in lit


def test_lamp_paths_do_not_open_capture():
    for rel in (
        "qoresence/deck/lease_lamp.py",
        "qoresence/deck/lease_lamp.js",
        "qoresence/deck/deck.html",
        "qoresence/deck/webrtc_hub.py",
        "qoresence/deck/live_paint.py",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "VideoCapture" not in text, f"{rel} must subscribe, not dual-open"
        assert "cv2.VideoCapture" not in text, f"{rel} must subscribe, not dual-open"


def test_env_opt_in_enables_lamp(monkeypatch):
    _on(monkeypatch)
    assert enabled() is True
    snap = snapshot(
        lease={"ok": True, "owner": "qoresence-streamer", "pid": 2, "device": "USB3.0 Video"},
        hub={"has_frame": True, "age_s": 0.3, "publishes": 4},
    )
    assert snap is not None
    assert snap["enabled"] is True
    assert snap["owner"] == "qoresence-streamer"
    assert snap["pid"] == 2
    assert snap["device"] == "USB3.0 Video"
    assert snap["subscribed"] is True
    assert snap["frames"] == 4
    assert snap["age_s"] == 0.3
