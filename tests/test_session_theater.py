"""Session Theater — fail-closed presentation of narrative-1 fixtures."""

from __future__ import annotations

from pathlib import Path

from qoresence.foundry.session_view import (
    FIXTURE_DIR,
    locked_value_html,
    normalize_pack,
    view_from_fixture,
)
from qoresence.mcp.server import TOOL_DEFS

DECK = Path(__file__).resolve().parents[1] / "qoresence" / "deck"
CIVIF_HTML = DECK / "civif.html"
SESSION_HTML = DECK / "session.html"
SESSION_JS = DECK / "session.js"


def test_event_record_reexport_and_mcp_untouched():
    from qoresence.core.civif_tick import EventRecord
    from qoresence.core.types import EventRecord as TypesEventRecord

    assert EventRecord is TypesEventRecord
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_narrative" not in names
    assert "export_clip" not in names
    assert "narrate_clip" in names


def test_civif_html_has_no_live_narrative_panel():
    blob = CIVIF_HTML.read_text(encoding="utf-8")
    assert "Event stream" not in blob
    assert "Session Theater" not in blob
    assert "coach-kind" in blob


def test_session_page_is_not_clip_docked():
    html = SESSION_HTML.read_text(encoding="utf-8")
    assert "clip-dock.js" not in html
    assert "LockedValue" in (DECK / "session.css").read_text(encoding="utf-8")
    js = SESSION_JS.read_text(encoding="utf-8")
    assert "function lockedValue" in js
    assert "board_locked" in js
    assert 'params.get("fixture") || "bodied_locked"' in js
    assert "/api/session/view" not in js
    assert "clip-dock.js" not in js


def test_bodied_locked_shows_digits_and_r2():
    view = view_from_fixture("bodied_locked")
    assert view["board_locked"] is True
    assert view["controller_bodied"] is True
    assert view["persisted"] is True
    assert view["confirmed"]["score"] == {"home": 21, "away": 14}
    assert view["confirmed"]["yard_line"] == 5
    html = locked_value_html(view["confirmed"])
    assert "LockedValue" in html
    assert "21–14" in html
    assert "5" in html
    types = [e["event_type"] for e in view["events"]]
    assert types == ["spam_window", "situation_shift", "press_to_score"]
    assert view["events"][0]["t_start_ns"] <= view["events"][1]["t_start_ns"]
    spam = view["events"][0]
    assert spam["input"]["button"] == "R2"
    assert spam["qualification"] == "confirmed"
    assert view["current_moment"]["event_type"] == "press_to_score"
    assert view["next_signal"]["kind"] == "coach"


def test_unlocked_strips_stuffed_score_and_yard():
    from qoresence.foundry.session_view import load_fixture

    raw = load_fixture("bodied_unlocked")
    assert raw["events"][0]["situation_summary"]["home_score"] == 99
    view = normalize_pack(raw)
    assert view["board_locked"] is False
    assert view["confirmed"]["score"] is None
    assert view["confirmed"]["yard_line"] is None
    html = locked_value_html(view["confirmed"])
    assert "99" not in html
    assert "LockedValue" not in html
    assert "Awaiting confirmed board state" in html
    blob = str(view)
    assert "99" not in blob
    for ev in view["events"]:
        assert ev["score"] is None
        assert ev["yard_line"] is None
        assert ev["qualification"] == "suppressed"


def test_unbodied_omits_hid_names():
    from qoresence.foundry.session_view import load_fixture

    raw = load_fixture("unbodied_locked")
    assert raw["events"][0]["input_summary"]["button"] == "R2"
    view = normalize_pack(raw)
    blob = str(view)
    assert "R2" not in blob
    spam = next(e for e in view["events"] if e["event_type"] == "spam_window")
    assert spam["input"] is None or "button" not in spam["input"]
    assert spam["qualification"] == "suppressed"
    shift = next(e for e in view["events"] if e["event_type"] == "situation_shift")
    assert shift["score"] == {"home": 21, "away": 14}
    assert shift["qualification"] == "confirmed"


def test_empty_not_persisted_vs_no_events():
    missing = view_from_fixture("empty_not_persisted")
    assert missing["empty_reason"] == "not_persisted"
    assert missing["persisted"] is False
    assert missing["events"] == []
    occurred = view_from_fixture("empty_persisted")
    assert occurred["empty_reason"] == "no_events"
    assert occurred["persisted"] is True


def test_persist_false_pack_without_path_is_not_persisted():
    view = normalize_pack(
        {
            "session_id": "s",
            "board_locked": True,
            "controller_bodied": True,
            "persisted": False,
            "events": [],
        }
    )
    assert view["persisted"] is False
    assert view["empty_reason"] == "not_persisted"


def test_unknown_event_type_is_generic_card():
    view = normalize_pack(
        {
            "session_id": "s",
            "board_locked": True,
            "controller_bodied": True,
            "persisted": True,
            "events": [
                {
                    "event_id": "s_evt_0001",
                    "event_type": "future_kind",
                    "t_start_ns": 10,
                    "t_end_ns": 10,
                    "situation_summary": {"home_score": 3, "away_score": 0, "yard_line": 40},
                }
            ],
        }
    )
    assert view["events"][0]["event_type"] == "future_kind"
    assert view["events"][0]["score"] == {"home": 3, "away": 0}


def test_session_routes_and_fixture(monkeypatch):
    from qoresence.deck.server import create_app

    try:
        from fastapi.testclient import TestClient
    except Exception:
        import pytest

        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(create_app())
    page = client.get("/session.html")
    assert page.status_code == 200
    assert "Session Theater" in page.text
    assert "clip-dock.js" not in page.text
    civ = client.get("/civif.html")
    assert civ.status_code == 200
    assert "Coach" in civ.text
    fx = client.get("/session_fixtures/bodied_unlocked.json")
    assert fx.status_code == 200
    assert fx.json()["events"][0]["situation_summary"]["home_score"] == 99
    missing = client.get("/session_fixtures/not_a_real_fixture.json")
    assert missing.status_code == 404
    traversal = client.get("/session_fixtures/%2e%2e%2fcivif.html")
    assert traversal.status_code in {404, 422}


def test_no_live_session_view_api():
    from qoresence.deck.server import create_app

    try:
        from fastapi.testclient import TestClient
    except Exception:
        import pytest

        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(create_app())
    r = client.get("/api/session/view")
    assert r.status_code == 404
    assert "civif_narrative" not in {t["name"] for t in TOOL_DEFS}


def test_fixtures_exist():
    names = {p.stem for p in FIXTURE_DIR.glob("*.json")}
    assert {
        "bodied_locked",
        "bodied_unlocked",
        "unbodied_locked",
        "empty_not_persisted",
        "empty_persisted",
    } <= names
