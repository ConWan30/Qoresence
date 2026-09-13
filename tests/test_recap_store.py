"""Recap from jsonl + default-OFF persist store. Accessible after Deck is down."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.foundry.recap_store import (
    PERSIST_ENV,
    persist_recap_at_stop,
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


def test_stop_once_writes_when_persist_env_unset(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(PERSIST_ENV, raising=False)
    monkeypatch.delenv("QORESENCE_QORACT_DOOR", raising=False)
    sid = "qoresence_stop_once"
    jsonl = tmp_path / "session.jsonl"
    rows = [
        _tick(1_000_000, sid=sid, home=13, away=0),
        _tick(2_000_000, sid=sid, home=22, away=0),
    ]
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    dest = tmp_path / "audits" / f"session-recap-{sid}.json"
    out = persist_recap_at_stop(session_id=sid, jsonl_path=jsonl, dest=dest)
    assert dest.is_file()
    assert out["path"]
    assert out.get("spawned") is False
    body = json.loads(dest.read_text(encoding="utf-8"))
    assert body["schema"] == "session-recap-1"
    assert body["session"] == sid
    assert body["event_count"] >= 1
    assert body["events"][-1]["score"] == {"home": 22, "away": 0}


def test_stop_once_uses_jsonl_tail(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(PERSIST_ENV, raising=False)
    sid = "qoresence_tail"
    jsonl = tmp_path / "session.jsonl"
    rows = [_tick(1, sid="old", home=99, away=99)]
    rows.extend(_tick(10 + i, sid=sid, home=7 + i, away=0) for i in range(3))
    jsonl.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    dest = tmp_path / "audits" / f"session-recap-{sid}.json"
    out = persist_recap_at_stop(session_id=sid, jsonl_path=jsonl, dest=dest)
    assert dest.is_file()
    assert out["path"]
    body = json.loads(dest.read_text(encoding="utf-8"))
    assert body["session"] == sid
    scores = [e["score"]["home"] for e in body["events"]]
    assert 99 not in scores


def test_stop_once_missing_jsonl_does_not_raise(tmp_path: Path, monkeypatch):
    monkeypatch.delenv(PERSIST_ENV, raising=False)
    dest = tmp_path / "audits" / "session-recap-missing.json"
    out = persist_recap_at_stop(
        session_id="gone",
        jsonl_path=tmp_path / "nope.jsonl",
        dest=dest,
    )
    assert "path" in out
    assert out.get("spawned") is False
    assert out.get("reason") == "no_jsonl"
    assert not dest.exists()


def test_stop_once_empty_session_is_miss(caplog):
    import logging

    caplog.set_level(logging.INFO)
    out = persist_recap_at_stop(session_id="")
    assert out["path"] is None
    assert out.get("reason") == "no_session"
    assert any("recap_stop miss reason=no_session" in r.message for r in caplog.records)


def test_stop_persists_before_running_guard():
    import inspect

    from qoresence.cli import QoresenceApp

    src = inspect.getsource(QoresenceApp.stop)
    persist_at = src.find("persist_recap_at_stop")
    guard_at = src.find("if not self._running")
    assert persist_at != -1
    assert guard_at != -1
    assert persist_at < guard_at


def test_default_audits_and_jsonl_are_repo_absolute():
    from qoresence.foundry import recap_store as rs

    assert rs.DEFAULT_AUDITS.is_absolute()
    assert rs.DEFAULT_JSONL.is_absolute()
    assert rs.DEFAULT_AUDITS.name == "audits"
    assert rs.DEFAULT_JSONL.name == "session.jsonl"
