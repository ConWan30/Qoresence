"""Read-only narrative event → existing clip_id linkage."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.foundry.session_view import (
    normalize_pack,
    permitted_clip_stem,
    resolve_event_clip,
)
from qoresence.mcp.server import TOOL_DEFS

DECK = Path(__file__).resolve().parents[1] / "qoresence" / "deck"


def _plant(root: Path, stem: str, *, session_id: str, sidecar: bool = True) -> None:
    (root / f"{stem}.mp4").write_bytes(b"ftyp")
    if sidecar:
        (root / f"{stem}.coupling.json").write_text(
            json.dumps({"clip_id": stem, "session_id": session_id}),
            encoding="utf-8",
        )


def _pack(session_id: str, clip_ids: list) -> dict:
    return {
        "session_id": session_id,
        "board_locked": True,
        "controller_bodied": True,
        "persisted": True,
        "events": [
            {
                "event_id": "e1",
                "event_type": "situation_shift",
                "session_id": session_id,
                "t_start_ns": 1,
                "situation_summary": {"home_score": 7, "away_score": 0, "yard_line": 20},
                "evidence": {"clip_ids": clip_ids, "coach_type": "situation"},
            }
        ],
    }


def test_permitted_stem_rejects_paths_and_aliases() -> None:
    assert permitted_clip_stem("hdmi_clip_20260822_101224") == "hdmi_clip_20260822_101224"
    assert permitted_clip_stem("hdmi_clip_20260822_101224.mp4") == "hdmi_clip_20260822_101224"
    assert permitted_clip_stem("hdmi_a") is None
    assert permitted_clip_stem("clip-1842-001") is None
    assert permitted_clip_stem("../hdmi_clip_20260822_101224") is None
    assert permitted_clip_stem("clips/hdmi_clip_20260822_101224.mp4") is None
    assert permitted_clip_stem("/etc/passwd") is None


def test_linked_clip_when_file_and_session_match(tmp_path: Path) -> None:
    stem = "hdmi_clip_20260822_101224"
    _plant(tmp_path, stem, session_id="1842")
    view = normalize_pack(_pack("1842", [stem]), clips_root=tmp_path)
    clip = view["events"][0]["clip"]
    assert clip == {"available": True, "clip_id": stem}
    assert "clip_ids" not in view["events"][0]
    assert "hdmi_a" not in str(view)


def test_unlinked_event_stays_usable(tmp_path: Path) -> None:
    view = normalize_pack(_pack("1842", []), clips_root=tmp_path)
    ev = view["events"][0]
    assert ev["clip"] == {"available": False}
    assert ev["score"] == {"home": 7, "away": 0}
    assert ev["event_type"] == "situation_shift"


def test_missing_file_and_cross_session_are_withheld(tmp_path: Path) -> None:
    missing = resolve_event_clip(["hdmi_clip_missing"], session_id="1842", clips_root=tmp_path)
    assert missing == {"available": False}
    stem = "hdmi_clip_other_session"
    _plant(tmp_path, stem, session_id="9999")
    cross = resolve_event_clip([stem], session_id="1842", clips_root=tmp_path)
    assert cross == {"available": False}


def test_malformed_sidecar_and_ids_are_withheld(tmp_path: Path) -> None:
    stem = "hdmi_clip_bad_sidecar"
    (tmp_path / f"{stem}.mp4").write_bytes(b"ftyp")
    (tmp_path / f"{stem}.coupling.json").write_text("{not-json", encoding="utf-8")
    assert resolve_event_clip([stem], session_id="1842", clips_root=tmp_path) == {"available": False}
    assert resolve_event_clip(["../etc/passwd"], session_id="1842", clips_root=tmp_path) == {
        "available": False
    }
    view = normalize_pack(_pack("1842", ["hdmi_a", "../x"]), clips_root=tmp_path)
    assert view["events"][0]["clip"] == {"available": False}
    assert "hdmi_a" not in json.dumps(view)


def test_fixture_hdmi_aliases_do_not_leak() -> None:
    from qoresence.foundry.session_view import view_from_fixture

    view = view_from_fixture("bodied_locked")
    dump = json.dumps(view)
    assert "hdmi_a" not in dump
    assert "hdmi_b" not in dump
    assert all(e["clip"]["available"] is False for e in view["events"])


def test_stale_envelope_keeps_existing_clip_does_not_invent(tmp_path: Path) -> None:
    from datetime import UTC, datetime, timedelta

    from qoresence.foundry import session_view as sv

    stem = "hdmi_clip_stale_keep"
    _plant(tmp_path, stem, session_id="1842")
    first = sv.normalize_pack(_pack("1842", [stem]), clips_root=tmp_path)
    env = {
        "ok": True,
        "status": "live",
        "session": "1842",
        "view": first,
        "freshness": {
            "generated_at": sv._iso_z(datetime.now(UTC) - timedelta(seconds=8)),
            "last_event_at": None,
            "age_ms": 8000,
            "stale": False,
        },
    }
    sv._last_envelope.clear()
    sv._last_envelope[sv._cache_key("1842", "")] = env

    def fail(_sid: str):
        return None, True

    orig = sv._load_live_pack
    sv._load_live_pack = fail  # type: ignore[method-assign]
    try:
        aged = sv.build_session_response(session_id="1842")
    finally:
        sv._load_live_pack = orig  # type: ignore[method-assign]
    assert aged["status"] == "live"
    assert aged["freshness"]["stale"] is True
    assert aged["view"]["events"][0]["clip"] == {"available": True, "clip_id": stem}


def test_invalid_envelope_has_no_clip_links() -> None:
    from qoresence.foundry import session_view as sv

    def bad(_sid: str):
        return {"events": {"nope": True}}, False

    orig = sv._load_live_pack
    sv._load_live_pack = bad  # type: ignore[method-assign]
    try:
        env = sv.build_session_response(session_id="broken")
    finally:
        sv._load_live_pack = orig  # type: ignore[method-assign]
    assert env["status"] == "invalid"
    assert env["view"]["events"] == []


def test_api_session_view_clip_and_media_target(tmp_path: Path, monkeypatch) -> None:
    from qoresence.deck.server import create_app
    from qoresence.vision import clip_buffer

    stem = "hdmi_clip_api_link"
    _plant(tmp_path, stem, session_id="1842")
    monkeypatch.setenv("QORESENCE_CLIPS_DIR", str(tmp_path))
    monkeypatch.setattr(clip_buffer, "DEFAULT_OUT_DIR", tmp_path)
    try:
        from fastapi.testclient import TestClient
    except Exception:
        import pytest

        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(create_app())
    body = {
        "session_id": "1842",
        "board_locked": True,
        "controller_bodied": True,
        "persisted": True,
        "events": [
            {
                "event_id": "e1",
                "event_type": "situation_shift",
                "t_start_ns": 1,
                "situation_summary": {"home_score": 3, "away_score": 0, "yard_line": 10},
                "evidence": {"clip_ids": [stem]},
            }
        ],
    }
    from qoresence.foundry.narrative_engine import generate_narrative

    generate_narrative("1842", ticks=[], persist=False)
    from qoresence.foundry import narrative_engine as ne

    ne._last["1842"] = body  # type: ignore[index]
    env = client.get("/api/session/view", params={"session_id": "1842"}).json()
    assert env["status"] == "live"
    clip = env["view"]["events"][0]["clip"]
    assert clip == {"available": True, "clip_id": stem}
    media = client.get(f"/media/clips/{stem}.mp4")
    assert media.status_code == 200
    assert client.get("/media/clips/../etc/passwd").status_code in {400, 404, 422}
    assert client.get("/media/clips/hdmi_a.mp4").status_code == 400
    js = (DECK / "session.js").read_text(encoding="utf-8")
    assert "/session_fixtures/" not in js
    assert "clip-dock.js" not in js
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_session_view" not in names
    assert "export_clip" not in names
    civif = (DECK / "civif.html").read_text(encoding="utf-8")
    assert "Session Theater" not in civif


def test_mcp_and_civif_html_untouched_by_clip_link() -> None:
    names = {t["name"] for t in TOOL_DEFS}
    assert "civif_narrative" not in names
    blob = (DECK / "civif.html").read_text(encoding="utf-8")
    assert "Session Theater" not in blob
    html = (DECK / "session.html").read_text(encoding="utf-8")
    assert "clip-dock.js" not in html
