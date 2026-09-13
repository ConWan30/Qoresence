"""Recap from jsonl + default-OFF persist store. Accessible after Deck is down."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.foundry.recap_store import (
    PERSIST_ENV,
    recap_from_jsonl,
    recap_from_ticks,
    write_session_recap,
)


def _tick(clock: int, *, sid: str, home: int, away: int, locked: bool = True) -> dict:
    return {
        "session_id": sid,
        "clock_ns": clock,
        "frame_seq": clock,
        "controller_bodied": False,
        "board_locked": locked,
        "situation": {
            "board_locked": locked,
            "home_score": home,
            "away_score": away,
        },
    }


def test_recap_from_jsonl_keeps_session_and_plate(tmp_path: Path):
    sid = "qoresence_jsonl_rebuild"
    jsonl = tmp_path / "session.jsonl"
    rows = [
        _tick(1_000_000, sid=sid, home=14, away=0),
        _tick(2_000_000, sid=sid, home=16, away=0),
        _tick(3_000_000, sid=sid, home=0, away=6),
        {"session_id": "other", "clock_ns": 9, "board_locked": True, "situation": {"home_score": 99, "away_score": 99}},
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    recap = recap_from_jsonl(jsonl, sid)
    assert recap["schema"] == "session-recap-1"
    assert recap["session"] == sid
    assert recap["ok"] is True
    assert recap["event_count"] == 2
    assert recap["events"][0]["score"] == {"home": 16, "away": 0}
    assert recap["events"][0]["qualification"] == "confirmed"
    assert recap["events"][-1]["score"] == {"home": 0, "away": 6}
    assert recap["events"][-1]["qualification"] == "plate"
    assert recap["events"][-1].get("not_final") is True


def test_persist_env_unset_does_not_write(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(PERSIST_ENV, raising=False)
    dest = tmp_path / "audits" / "session-recap-x.json"
    recap = recap_from_ticks("x", [_tick(1, sid="x", home=7, away=0)])
    out = write_session_recap(recap, dest, enabled=False)
    assert out is None
    assert not dest.exists()


def test_persist_enabled_writes_file_readable_after(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(PERSIST_ENV, "1")
    dest = tmp_path / "audits" / "session-recap-y.json"
    recap = recap_from_ticks("y", [_tick(1, sid="y", home=13, away=0), _tick(2, sid="y", home=16, away=0)])
    path = write_session_recap(recap, dest)
    assert path is not None
    assert path.is_file()
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["schema"] == "session-recap-1"
    assert body["session"] == "y"
    assert body["event_count"] >= 1
