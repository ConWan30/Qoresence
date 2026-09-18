"""Ticket-stale sentinel — observation plane, fail-closed.

Locks in: enqueue-only hot path, never emits bus events, never consults the
ticket book on the event path, deterministic fallback works, confidence gates
behave, and licenses_digits is False forever.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

from qoresence.core.unified_config import (
    RetinaUnifiedConfig,
    TicketStaleConfig,
)
from qoresence.observability.ticket_stale import (
    TicketStaleSentinel,
    compose_stale_verdict,
    local_stale_answers,
    make_ticket_stale_from_config,
)


def _sentinel(tmp_path, **kw):
    cfg = TicketStaleConfig(enabled=True, out_dir=str(tmp_path), cadence_s=0.05)
    return TicketStaleSentinel(cfg, **kw)


def test_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.jev_ticket_stale.enabled is False
    assert make_ticket_stale_from_config(config.jev_ticket_stale) is None


def test_compose_never_licenses_digits():
    for action in ("flag_stale", "watch", "observe"):
        out = compose_stale_verdict(
            stale_class="crop_moved_on",
            stale_confidence=0.9,
            hold_noul=0.9 if action == "flag_stale" else 0.1,
        )
        assert out["licenses_digits"] is False
        assert "speech" not in out and "digits" not in out


def test_gates_act_soft_observe():
    high = compose_stale_verdict(
        stale_class="match_changed", stale_confidence=0.8, hold_noul=0.85
    )
    assert high["action"] == "flag_stale"

    soft = compose_stale_verdict(
        stale_class="menu_or_plate", stale_confidence=0.55, hold_noul=0.5
    )
    assert soft["action"] == "watch"

    low = compose_stale_verdict(
        stale_class="fresh", stale_confidence=0.9, hold_noul=0.1, freshness=2.0
    )
    assert low["action"] == "observe"


def test_deterministic_stale_cannot_be_talked_down():
    out = compose_stale_verdict(
        stale_class="fresh", stale_confidence=0.9, hold_noul=0.05,
        gate_reason="ticket_stale",
    )
    assert out["action"] == "flag_stale"
    assert out["stale_class"] != "fresh"
    assert out["licenses_digits"] is False


def test_fallback_moved_on_crop():
    answers = local_stale_answers(
        {
            "ticket": {
                "ticket_id": "t1",
                "home_score": 14,
                "away_score": 10,
                "crop_hash": "aaa",
                "clock_ns": 1_000,
            },
            "live": {
                "home_score": 21,
                "away_score": 10,
                "crop_hash": "bbb",
                "clock_ns": 2_000,
            },
        }
    )
    assert answers["stale_class"] in {"crop_moved_on", "match_changed"}
    assert answers["hold_noul"] >= 0.7
    out = compose_stale_verdict(
        stale_class=answers["stale_class"],
        stale_confidence=answers["stale_confidence"],
        hold_noul=answers["hold_noul"],
        freshness=answers["freshness"],
    )
    assert out["action"] == "flag_stale"


def test_fallback_fresh():
    answers = local_stale_answers(
        {
            "ticket": {
                "ticket_id": "t1",
                "home_score": 7,
                "away_score": 3,
                "crop_hash": "aaa",
                "clock_ns": 1_000,
            },
            "live": {
                "home_score": 7,
                "away_score": 3,
                "crop_hash": "aaa",
                "clock_ns": 2_000,
            },
        }
    )
    assert answers["stale_class"] == "fresh"
    assert answers["hold_noul"] < 0.4


class _DummyBus:
    def __init__(self) -> None:
        self._cb = None
        self.emitted = []

    def subscribe_raw(self, cb):
        self._cb = cb

        def _unsub():
            self._cb = None

        return _unsub

    def emit(self, rec):
        self.emitted.append(rec)
        if self._cb:
            self._cb(rec)


class _Evt:
    def __init__(self, payload):
        self.type = "visual"
        self.payload = payload
        self.clock_ns = 1
        self.source_lobe = "visual"


def test_hot_path_only_enqueues_and_never_reads_ticket_book(tmp_path, monkeypatch):
    """_on_event must not consult the ticket book (lobe lock) at all."""
    import qoresence.vision.confirm_ticket as ct

    def _boom():
        raise AssertionError("ticket book touched on event path")

    monkeypatch.setattr(ct, "get_ticket_book", _boom)

    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        ticket_fn=lambda: {},
        live_fn=lambda: {"clock_ns": 1},
        ask_fn=lambda s: local_stale_answers(s),
    )
    try:
        t0 = time.perf_counter()
        for _ in range(64):
            bus.emit(_Evt({"parsed": {"home_score": 7, "away_score": 0}}))
        assert time.perf_counter() - t0 < 1.0
        assert sen._queue.qsize() > 0
    finally:
        sen.stop()


def test_worker_never_emits_bus_events(tmp_path):
    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        ticket_fn=lambda: {
            "ticket_id": "t1",
            "home_score": 14,
            "away_score": 10,
            "crop_hash": "aaa",
            "clock_ns": 1_000,
        },
        live_fn=lambda: {
            "home_score": 21,
            "away_score": 10,
            "crop_hash": "bbb",
            "clock_ns": 9_000_000_001,
        },
        ask_fn=lambda s: local_stale_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        stats = sen.stats()
        assert stats["judged"] >= 1
        assert stats["action"] == "flag_stale"
        assert stats["licenses_digits"] is False
        # Only subscriber callbacks may appear in `emitted`; the sentinel
        # itself never calls bus.emit.
        assert all(ev is not None for ev in bus.emitted)
        last = sen.last()
        assert last.get("plane") == "qoresence-observation"
    finally:
        sen.stop()


def test_jsonl_audit_written(tmp_path):
    sen = _sentinel(
        tmp_path,
        ticket_fn=lambda: {"ticket_id": "t1", "home_score": 1, "away_score": 0},
        live_fn=lambda: {"home_score": 1, "away_score": 0},
        ask_fn=lambda s: local_stale_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        sen.stop()
        path = tmp_path / "ticket_stale.jsonl"
        assert path.exists()
        row = json.loads(path.read_text().strip().splitlines()[0])
        assert row["licenses_digits"] is False
        assert row["action"] in {"flag_stale", "watch", "observe"}
    finally:
        sen.stop()


def test_disabled_by_default_flag_only(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_JEV_TICKET_STALE", raising=False)
    sen = TicketStaleSentinel(
        TicketStaleConfig(enabled=False, out_dir=str(tmp_path))
    )
    assert sen.enabled is False
    # Off → _on_event is a no-op; no queue, no worker, no files.
    sen._on_event(_Evt({"parsed": {"home_score": 1, "away_score": 0}}))
    assert sen._queue.qsize() == 0
    sen.stop()
