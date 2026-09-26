"""Qoredev landing sequence — observation plane, query-only."""

from __future__ import annotations

from pathlib import Path

from qoresence.operator_bus.qoredev import (
    SCHEMA,
    STEPS,
    clock_from_stamps,
    glass_from_deck,
    lock_from_tickets,
    physical_from_video,
    qoredev_health,
    sequence_from_snapshot,
    story_from_pack,
)


LIVE = {
    "video": {"age_s": 0.04, "has_frame": True, "frames": 800, "seq": 12, "clock_ns": 9},
    "situation": {
        "clock_ns": 9,
        "frame_seq": 12,
        "confirm_ticket_id": "c-1",
        "score_vlm_locked": True,
        "home_score": 23,
        "away_score": 22,
    },
    "clients": 1,
    "glass": {"js": "index-abc.js", "path": "/tmp/deck.html"},
    "story": {"status": "empty", "event_count": 0},
}


def test_steps_are_the_five_landing_names():
    assert STEPS == ("physical", "clock", "lock", "glass", "story")


def test_physical_live_when_age_fresh():
    rec = physical_from_video({"age_s": 0.08, "has_frame": True, "frames": 40})
    assert rec["licensed"] is True
    assert rec["kind"] == "live"
    assert rec["path"] == "fast"


def test_physical_freeze_when_age_climbs():
    rec = physical_from_video({"age_s": 6.2, "has_frame": True, "frames": 40})
    assert rec["licensed"] is False
    assert rec["kind"] == "freeze"


def test_clock_ticking_without_hid():
    rec = clock_from_stamps(11, 7)
    assert rec["licensed"] is True
    assert rec["kind"] == "ticking"
    assert "pll_lock" not in rec["evidence"]
    assert "binds" not in rec["evidence"]


def test_clock_dark_without_seq():
    rec = clock_from_stamps(11, None)
    assert rec["licensed"] is False
    assert rec["kind"] == "no_seq"


def test_lock_requires_ticket_and_flag():
    veto = lock_from_tickets(confirm_ticket_id="", score_vlm_locked=True)
    assert veto["licensed"] is False
    assert veto["kind"] == "flag_only"
    ok = lock_from_tickets(confirm_ticket_id="t-9", score_vlm_locked=True)
    assert ok["licensed"] is True
    assert ok["kind"] == "licensed"
    assert ok["path"] == "confirm"


def test_glass_spa_licenses_without_clients():
    rec = glass_from_deck(0, {"js": "index-xyz.js"})
    assert rec["licensed"] is True
    assert rec["kind"] == "spa"


def test_glass_dark_without_spa_or_clients():
    rec = glass_from_deck(0, {"js": "none"})
    assert rec["licensed"] is False
    assert rec["kind"] == "dark"


def test_story_empty_is_honest_and_licensed():
    rec = story_from_pack({"status": "not_persisted", "event_count": 0})
    assert rec["licensed"] is True
    assert rec["kind"] == "empty"


def test_story_persisted_when_events():
    rec = story_from_pack({"status": "live", "event_count": 3, "schema": "narrative-1"})
    assert rec["kind"] == "persisted"


def test_sequence_hold_when_four_live_and_story_empty():
    seq = sequence_from_snapshot(LIVE)
    assert seq["schema"] == SCHEMA
    assert seq["plane"] == "qoresence-observation"
    assert seq["from"] == "qoredev"
    assert seq["next"] == "hold"
    assert seq["path"] == "fast"
    assert "HOLD" in seq["text"]
    names = [s["name"] for s in seq["steps"]]
    assert names == list(STEPS)


def test_fast_path_strips_score_digits():
    seq = sequence_from_snapshot(LIVE)
    blob = str(seq)
    assert "23" not in blob
    assert "22" not in blob
    assert "home_score" not in blob
    assert "away_score" not in blob
    assert seq["steps"][2]["evidence"]["score_vlm_locked"] is True


def test_next_physical_on_freeze():
    snap = dict(LIVE)
    snap["video"] = {"age_s": 8.0, "has_frame": True, "frames": 3, "seq": 1, "clock_ns": 2}
    seq = sequence_from_snapshot(snap)
    assert seq["next"] == "physical"
    assert "freeze" in seq["text"]


def test_next_clock_when_no_seq():
    snap = {
        "video": {"age_s": 0.02, "has_frame": True, "frames": 9, "clock_ns": 4},
        "situation": {"clock_ns": 4, "confirm_ticket_id": "c", "score_vlm_locked": True},
        "clients": 1,
        "glass": {"js": "index-a.js"},
        "story": {"status": "empty"},
    }
    seq = sequence_from_snapshot(snap)
    assert seq["next"] == "clock"


def test_next_lock_when_unlocked():
    snap = dict(LIVE)
    snap["situation"] = {"clock_ns": 9, "frame_seq": 12, "score_vlm_locked": False}
    seq = sequence_from_snapshot(snap)
    assert seq["next"] == "lock"
    assert seq["path"] == "confirm"


def test_next_glass_when_deck_dark():
    snap = dict(LIVE)
    snap["clients"] = 0
    snap["glass"] = {"js": "none", "path": ""}
    seq = sequence_from_snapshot(snap)
    assert seq["next"] == "glass"


def test_source_is_observation_only():
    src = Path(__file__).resolve().parents[1] / "qoresence" / "operator_bus" / "qoredev.py"
    text = src.read_text(encoding="utf-8")
    for banned in (
        "emit_raw(",
        "A2ABus(",
        "hidapi",
        "whip",
        "rtmp",
        "x-glass",
        "--play",
        "VideoCapture",
        "hid_by_seq",
        "DualSense",
    ):
        assert banned not in text


def test_qoredev_health_fail_closed():
    out = qoredev_health(None)
    assert out["schema"] == SCHEMA
    assert out["plane"] == "qoresence-observation"
    assert out["next"] in {"physical", "clock", "lock", "glass", "hold"}


def test_prompt_is_qoredev_and_hold():
    from qoresence.operator_bus.prompt import QOREDEV_BUS_PROMPT

    assert "Qoredev" in QOREDEV_BUS_PROMPT
    assert "physical → clock → lock → glass → story" in QOREDEV_BUS_PROMPT
    assert "GO MERGE" in QOREDEV_BUS_PROMPT
    assert "DualSense" in QOREDEV_BUS_PROMPT
    assert "--x-glass" in QOREDEV_BUS_PROMPT
    assert "RetinaEventBus" in QOREDEV_BUS_PROMPT
    assert "/api/operator/qoredev" in QOREDEV_BUS_PROMPT


def test_health_and_operator_route_expose_qoredev():
    from qoresence.deck import server as deck_server

    app = deck_server.create_app()
    if app is None:
        import pytest

        pytest.skip("fastapi not installed")
    try:
        from fastapi.testclient import TestClient
    except Exception:
        import pytest

        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(app)
    health = client.get("/health").json()
    assert health["ok"] is True
    assert health["qoredev"]["schema"] == SCHEMA
    assert health["qoredev"]["from"] == "qoredev"
    assert health["qoredev"]["plane"] == "qoresence-observation"
    q = client.get("/api/operator/qoredev").json()
    assert q["ok"] is True
    assert q["sequence"]["schema"] == SCHEMA
    assert "Qoredev" in q["prompt"]
    prompt = client.get("/api/operator/bus/prompt", params={"bot": "qoredev"}).json()
    assert prompt["to"] == "qoredev"
    assert "physical → clock → lock → glass → story" in prompt["prompt"]
