"""Read-only session-recap-1 derived from the normalized session view."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.foundry.session_view import (
    build_session_recap,
    recap_from_envelope,
    view_from_fixture,
)
from qoresence.mcp.server import TOOL_DEFS

DECK = Path(__file__).resolve().parents[1] / "qoresence" / "deck"


def _env(view: dict, *, status: str = "live", session: str = "s") -> dict:
    return {
        "ok": True,
        "status": status,
        "session": session,
        "view": view,
        "freshness": {
            "generated_at": "2026-08-25T00:00:00Z",
            "last_event_at": None,
            "age_ms": 0,
            "stale": False,
        },
    }


def test_recap_fixture_live_counts() -> None:
    recap = build_session_recap(fixture="bodied_locked")
    assert recap["schema"] == "session-recap-1"
    assert recap["ok"] is True
    assert recap["status"] == "live"
    assert recap["event_count"] == 3
    assert recap["confirmed_event_count"] == 3
    assert recap["linked_clip_count"] == 0
    assert recap["duration_ms"] == 13_000
    assert recap["incomplete"] is False
    assert recap["empty_reason"] is None
    assert recap["freshness"]["stale"] is False
    ids = [e["event_id"] for e in recap["events"]]
    assert ids == ["1842_evt_0001", "1842_evt_0002", "1842_evt_0003"]
    assert all("situation_summary" not in e for e in recap["events"])
    assert all("clip_ids" not in e for e in recap["events"])


def test_recap_empty_and_not_persisted() -> None:
    empty = build_session_recap(fixture="empty_persisted")
    assert empty["status"] == "empty"
    assert empty["empty_reason"] == "no_events"
    assert empty["event_count"] == 0
    assert empty["duration_ms"] is None
    assert empty["incomplete"] is False
    missing = build_session_recap(fixture="empty_not_persisted")
    assert missing["status"] == "not_persisted"
    assert missing["empty_reason"] == "not_persisted"
    assert missing["incomplete"] is False


def test_recap_unavailable_and_invalid() -> None:
    unavail = build_session_recap(fixture="narrative_prod")
    assert unavail["status"] == "unavailable"
    assert unavail["ok"] is True
    assert unavail["empty_reason"] is None
    assert unavail["incomplete"] is False
    assert "freshness" in unavail
    from qoresence.foundry import session_view as sv

    def bad(_sid: str):
        return {"events": {"nope": True}}, False

    orig = sv._load_live_pack
    sv._load_live_pack = bad  # type: ignore[method-assign]
    try:
        inv = build_session_recap(session_id="broken")
    finally:
        sv._load_live_pack = orig  # type: ignore[method-assign]
    assert inv["status"] == "invalid"
    assert inv["ok"] is False
    assert inv["events"] == []
    assert inv["event_count"] == 0
    assert inv["incomplete"] is False
    assert inv["empty_reason"] is None
    assert inv["freshness"]["stale"] is False
    assert inv["freshness"]["last_event_at"] is None


def test_recap_clock_edge_cases() -> None:
    from qoresence.foundry.session_view import normalize_pack

    view = normalize_pack(
        {
            "session_id": "s",
            "board_locked": True,
            "controller_bodied": True,
            "persisted": True,
            "events": [
                {"event_id": "b", "event_type": "situation_shift", "t_start_ns": 3_000_000, "t_end_ns": 4_000_000},
                {"event_id": "a", "event_type": "situation_shift", "t_start_ns": 1_000_000, "t_end_ns": 1_000_000},
                {"event_id": "z", "event_type": "situation_shift", "t_start_ns": 0, "t_end_ns": 9_000_000},
                {"event_id": "r", "event_type": "situation_shift", "t_start_ns": 8_000_000, "t_end_ns": 2_000_000},
                {"event_id": "n", "event_type": "situation_shift", "t_start_ns": -5, "t_end_ns": 2},
            ],
        }
    )
    recap = recap_from_envelope(_env(view))
    assert [e["event_id"] for e in recap["events"]] == ["a", "b", "r", "n", "z"]
    assert recap["duration_ms"] == 3
    assert recap["event_count"] == 5
    none = recap_from_envelope(
        _env(
            normalize_pack(
                {
                    "session_id": "s",
                    "persisted": True,
                    "board_locked": True,
                    "controller_bodied": True,
                    "events": [{"event_id": "x", "event_type": "x", "t_start_ns": 0, "t_end_ns": 0}],
                }
            )
        )
    )
    assert none["duration_ms"] is None


def test_recap_stale_does_not_change_counts() -> None:
    from datetime import UTC, datetime, timedelta

    from qoresence.foundry import session_view as sv

    first = sv.build_session_response(fixture="bodied_locked", session_id="1842")
    recap_a = recap_from_envelope(first)
    aged = dict(first)
    aged["freshness"] = dict(first["freshness"])
    aged["freshness"]["generated_at"] = sv._iso_z(datetime.now(UTC) - timedelta(seconds=8))
    sv._last_envelope[sv._cache_key("1842", "")] = aged

    def fail(_sid: str):
        return None, True

    orig = sv._load_live_pack
    sv._load_live_pack = fail  # type: ignore[method-assign]
    try:
        recap_b = build_session_recap(session_id="1842")
    finally:
        sv._load_live_pack = orig  # type: ignore[method-assign]
    assert recap_b["status"] == "live"
    assert recap_b["freshness"]["stale"] is True
    assert recap_b["event_count"] == recap_a["event_count"]
    assert recap_b["confirmed_event_count"] == recap_a["confirmed_event_count"]
    assert recap_b["linked_clip_count"] == recap_a["linked_clip_count"]


def test_recap_does_not_persist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    recap = build_session_recap(session_id="no-write")
    assert recap["schema"] == "session-recap-1"
    assert not list(tmp_path.glob("**/narrative_*.json"))


def test_recap_http_and_boundaries() -> None:
    from qoresence.deck.server import create_app

    try:
        from fastapi.testclient import TestClient
    except Exception:
        import pytest

        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(create_app())
    live = client.get("/api/session/recap", params={"fixture": "bodied_locked"}).json()
    assert live["schema"] == "session-recap-1"
    assert live["event_count"] == 3
    assert "99" not in json.dumps(live)
    empty = client.get("/api/session/recap", params={"fixture": "empty_persisted"}).json()
    assert empty["status"] == "empty"
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_recap" not in names
    assert "export_clip" not in names
    html = (DECK / "session.html").read_text(encoding="utf-8")
    js = (DECK / "session.js").read_text(encoding="utf-8")
    assert "Recap" in html
    assert "/api/session/recap" in js
    assert "/session_fixtures/" not in js
    assert "clip-dock.js" not in html
    assert "Session Theater" not in (DECK / "civif.html").read_text(encoding="utf-8")
