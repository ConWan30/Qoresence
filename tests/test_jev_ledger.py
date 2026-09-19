"""Unified Jev judgment ledger — one append-only sink, fail-closed.

Locks in: append/read roundtrip on ``qoresence.jev.ledger.v0``, pack tag
validation (unknown pack rejected, nothing written), ``licenses_digits`` is
False on every row forever (and scrubbed inside payloads), default-OFF gating
(flag/env or the --jev umbrella), and pack dual-write keeps private JSONL.
"""

from __future__ import annotations

import json

import pytest

from qoresence.observability.jev_ledger import (
    JevLedger,
    append_judgment,
    configure_jev_ledger,
    ledger_enabled,
    note_judgment,
    read_judgments,
    reset_jev_ledger,
    PACKS,
    PLANE,
    SCHEMA,
)


@pytest.fixture(autouse=True)
def _clean_ledger(monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_JEV_LEDGER", raising=False)
    reset_jev_ledger()
    yield
    reset_jev_ledger()


def test_row_shape_roundtrip(tmp_path):
    path = tmp_path / "jev_ledger.jsonl"
    ledger = JevLedger(path)
    try:
        ok = ledger.append(
            "ticket_stale",
            {"action": "flag_stale", "stale_class": "crop_moved_on"},
            clock_ns=123_000,
            frame_seq=7,
        )
        assert ok is True
    finally:
        ledger.close()
    rows = list(read_judgments(path))
    assert len(rows) == 1
    row = rows[0]
    assert row["schema"] == SCHEMA == "qoresence.jev.ledger.v0"
    assert row["plane"] == PLANE == "qoresence-observation"
    assert row["pack"] == "ticket_stale"
    assert row["clock_ns"] == 123_000
    assert row["frame_seq"] == 7
    assert row["licenses_digits"] is False
    assert row["verdict"]["action"] == "flag_stale"
    assert isinstance(row["ts"], float)


def test_clock_fields_pulled_from_verdict(tmp_path):
    ledger = JevLedger(tmp_path / "l.jsonl")
    try:
        ledger.append("noul", {"clock_ns": 55, "frame_seq": 3, "hud_kind": "live_hud"})
    finally:
        ledger.close()
    (row,) = list(read_judgments(tmp_path / "l.jsonl"))
    assert row["clock_ns"] == 55
    assert row["frame_seq"] == 3


def test_licenses_digits_false_forever(tmp_path):
    ledger = JevLedger(tmp_path / "l.jsonl")
    try:
        ledger.append("mint_verifier", {"action": "remint", "licenses_digits": True})
    finally:
        ledger.close()
    (row,) = list(read_judgments(tmp_path / "l.jsonl"))
    assert row["licenses_digits"] is False
    assert row["verdict"]["licenses_digits"] is False


def test_unknown_pack_rejected_no_write(tmp_path):
    path = tmp_path / "l.jsonl"
    ledger = JevLedger(path)
    try:
        assert ledger.append("not_a_pack", {"a": 1}) is False
        assert ledger.append("", {"a": 1}) is False
    finally:
        ledger.close()
    assert not path.exists()
    assert ledger.stats()["rejected"] == 2


def test_packs_covers_existing_and_reserved_names():
    for name in (
        "ticket_stale",
        "noul",
        "jev_conductor",
        "conductor",
        "press_labeler",
        "recap_hygiene",
        "sync_coroner",
        "score_plausibility",
        "ticket_glass",
        "sync_glass",
        "mint_verifier",
        "join_picker",
        "connector",
    ):
        assert name in PACKS


def test_module_append_default_off(tmp_path):
    configure_jev_ledger(path=tmp_path / "l.jsonl")
    assert ledger_enabled() is False
    assert append_judgment("ticket_stale", {"action": "observe"}) is False
    assert not (tmp_path / "l.jsonl").exists()


def test_module_append_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_JEV_LEDGER", "1")
    configure_jev_ledger(path=tmp_path / "l.jsonl")
    assert note_judgment("noul", {"hud_kind": "menu"}) is True
    reset_jev_ledger()
    (row,) = list(read_judgments(tmp_path / "l.jsonl"))
    assert row["pack"] == "noul"
    assert row["licenses_digits"] is False


def test_jev_umbrella_enables_ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_JEV", "1")
    assert ledger_enabled() is True
    configure_jev_ledger(path=tmp_path / "l.jsonl")
    assert append_judgment("sync_coroner", {"bottleneck": "healthy"}) is True


def test_append_never_raises(tmp_path):
    ledger = JevLedger(tmp_path / "l.jsonl")
    try:
        assert ledger.append("ticket_stale", {"bad": object()}) is True  # default=str
        assert ledger.append("ticket_stale", None) is True
    finally:
        ledger.close()


def test_pack_dual_write_keeps_private_jsonl(tmp_path, monkeypatch):
    """ticket_stale _write_jsonl writes both its own file and the ledger."""
    from qoresence.core.unified_config import TicketStaleConfig
    from qoresence.observability.ticket_stale import TicketStaleSentinel

    monkeypatch.setenv("QORESENCE_JEV_LEDGER", "1")
    configure_jev_ledger(path=tmp_path / "jev_ledger.jsonl")
    sen = TicketStaleSentinel(
        TicketStaleConfig(enabled=True, out_dir=str(tmp_path / "pack"))
    )
    try:
        sen._write_jsonl({"action": "watch", "clock_ns": 9})
    finally:
        sen.stop()
        reset_jev_ledger()
    private = json.loads(
        (tmp_path / "pack" / "ticket_stale.jsonl").read_text().strip()
    )
    (row,) = list(read_judgments(tmp_path / "jev_ledger.jsonl"))
    assert private["action"] == "watch"
    assert row["pack"] == "ticket_stale"
    assert row["verdict"]["action"] == "watch"
    assert row["clock_ns"] == 9
