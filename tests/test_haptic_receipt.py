"""Three-rail haptic receipt — fail-closed join of HID, HDMI lock, haptic-out."""

from __future__ import annotations

import time

from qoresence.core.civif_tick import CoupledTickRecord, SituationSnapshot
from qoresence.sync.haptic_receipt import (
    RECEIPT_SCHEMA,
    HapticReceiptClock,
    build_receipt,
    receipt_from_tick_and_obs,
    recent_receipts,
    reset_receipt_clock,
    start_receipt_clock,
    validate_receipt,
)
from qoresence.sync.haptic_schema import HAPTIC_PLANE, empty_record


def setup_function() -> None:
    reset_receipt_clock()


def teardown_function() -> None:
    reset_receipt_clock()


def _tick(
    *,
    bodied: bool = True,
    board_locked: bool = True,
    home: int | None = 21,
    away: int | None = 17,
    ticket: str = "ct_1",
    score_vlm_locked: bool = True,
) -> dict:
    sit = SituationSnapshot(home_score=home, away_score=away) if board_locked else None
    rec = CoupledTickRecord(
        session_id="sess",
        clock_ns=5_000_000_000,
        frame_seq=12,
        input_ticks=[],
        situation=sit,
        board_locked=board_locked,
        controller_bodied=bodied,
        body_reason="usb" if bodied else "pad_not_on_this_host",
    ).to_dict()
    snap = rec.get("situation_snapshot") or {}
    if isinstance(snap, dict):
        snap["confirm_ticket_id"] = ticket
        snap["score_vlm_locked"] = score_vlm_locked
        rec["situation_snapshot"] = snap
    rec["score_vlm_locked"] = score_vlm_locked
    return rec


def _obs(*, channel: str = "hid_output", hid: bool = True) -> dict:
    return {
        "schema_version": "haptic_obs-1",
        "plane": HAPTIC_PLANE,
        "session_id": "sess",
        "kind": "haptic_transient",
        "channel": channel,
        "t_start_ns": 5_010_000_000,
        "coupled": hid,
        "provenance": {"coupling_reason": "hid_reports_this_host" if hid else "unattributed"},
        "licenses": {"haptics_observed": True, "haptics_coupled": hid},
    }


def test_three_rails_couple_only_when_all_license():
    rec = receipt_from_tick_and_obs(_tick(), _obs())
    assert rec["schema_version"] == RECEIPT_SCHEMA
    assert rec["kind"] == "haptic_receipt"
    assert rec["coupled"] is True
    assert rec["rails"]["hid_in"]["licensed"] is True
    assert rec["rails"]["hdmi_lock"]["licensed"] is True
    assert rec["rails"]["haptic_out"]["licensed"] is True
    assert rec["rails"]["haptic_out"]["channel"] == "hid_output"
    assert rec["score"] == {"home": 21, "away": 17}
    assert rec["licenses"]["haptics_coupled"] is True
    assert rec["licenses"]["haptics_confirmed"] is False
    assert rec["public_surfaces"] is False
    assert "controller_bodied" not in rec
    assert validate_receipt(rec) == []


def test_ps5_bound_pad_stays_dark():
    """Charge-cable / console BT: empty HID and no output sniff → dark receipt."""
    rec = receipt_from_tick_and_obs(
        _tick(bodied=False),
        empty_record(session_id="sess", clock_ns=5_000_000_000, reason="ps5_bt_no_usb_out"),
    )
    assert rec["kind"] == "haptic_receipt_dark"
    assert rec["coupled"] is False
    assert rec["rails"]["hid_in"]["licensed"] is False
    assert rec["rails"]["haptic_out"]["licensed"] is False
    assert rec["rails"]["haptic_out"]["channel"] == "unavailable"
    assert rec["licenses"]["haptics_observed"] is False
    assert rec["licenses"]["haptics_confirmed"] is False
    assert validate_receipt(rec) == []


def test_hdmi_lock_without_ticket_does_not_couple_or_leak_digits():
    rec = receipt_from_tick_and_obs(
        _tick(ticket="", score_vlm_locked=True, board_locked=True),
        _obs(),
    )
    assert rec["rails"]["hdmi_lock"]["licensed"] is False
    assert rec["rails"]["hdmi_lock"]["reason"] == "lock_without_ticket"
    assert rec["coupled"] is False
    assert rec["score"] == {"home": None, "away": None}
    assert validate_receipt(rec) == []


def test_imu_echo_is_a_licensed_haptic_channel():
    rec = receipt_from_tick_and_obs(_tick(), _obs(channel="imu_echo"))
    assert rec["rails"]["haptic_out"]["channel"] == "imu_echo"
    assert rec["coupled"] is True
    assert validate_receipt(rec) == []


def test_missing_hid_blocks_coupling_even_with_lock_and_pulse():
    rec = receipt_from_tick_and_obs(_tick(bodied=False), _obs(hid=False))
    assert rec["rails"]["hid_in"]["licensed"] is False
    assert rec["coupled"] is False
    assert rec["score"] == {"home": 21, "away": 17}
    assert validate_receipt(rec) == []


def test_build_receipt_does_not_write_controller_bodied():
    rec = build_receipt(
        session_id="s",
        clock_ns=1,
        host_has_hid_reports=True,
        board_locked=True,
        score_vlm_locked=True,
        confirm_ticket_id="ct",
        haptic_channel="hid_output",
        haptic_observed=True,
        situation={"home_score": 3, "away_score": 0},
    )
    assert "controller_bodied" not in rec
    assert rec["licenses"]["haptics_signature_known"] is False
    assert validate_receipt(rec) == []


def test_validate_rejects_digits_without_hdmi_license():
    rec = build_receipt(haptic_observed=False)
    rec["score"] = {"home": 7, "away": 0}
    assert "digits_without_hdmi_license" in validate_receipt(rec)


def test_live_clock_joins_tick_and_obs(tmp_path):
    path = tmp_path / "receipt.jsonl"
    clock = HapticReceiptClock(persist=True, jsonl_path=path)
    try:
        clock.note_tick(_tick())
        clock.note_obs(_obs())
        clock.flush(timeout_s=2.0)
        rec = clock.last()
        assert rec is not None
        assert rec["coupled"] is True
        assert rec["kind"] == "haptic_receipt"
        assert rec["public_surfaces"] is False
        assert validate_receipt(rec) == []
        dumped = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert dumped
    finally:
        clock.stop()


def test_live_clock_stale_obs_does_not_couple():
    clock = HapticReceiptClock(persist=False, window_ms=120.0)
    try:
        tick = _tick()
        tick["clock_ns"] = 5_000_000_000
        obs = _obs()
        obs["t_start_ns"] = 8_000_000_000
        clock.note_tick(tick)
        clock.note_obs(obs)
        clock.flush(timeout_s=2.0)
        rec = clock.last()
        assert rec is not None
        assert rec["rails"]["haptic_out"]["licensed"] is False
        assert rec["coupled"] is False
    finally:
        clock.stop()


def test_live_clock_hot_path_does_not_block_when_worker_stalled():
    clock = HapticReceiptClock(persist=False, queue_size=8, stall_worker=True)
    try:
        start = time.perf_counter()
        for _i in range(2000):
            clock.note_tick(_tick())
        elapsed = time.perf_counter() - start
        assert elapsed < 0.75, f"hot path blocked ({elapsed:.3f}s)"
    finally:
        clock.stop()


def test_cer_observe_enqueues_receipt_without_bus():
    from qoresence.core import RetinaEventBus
    from qoresence.foundry.cer_log import CerLog

    clock = start_receipt_clock(persist=False, clock=HapticReceiptClock(persist=False))
    bus = RetinaEventBus(session_id="cer_receipt", jsonl_path=None, enable_ws=False)
    seen: list[str] = []
    bus.subscribe(lambda ev: seen.append(str(getattr(ev, "type", ev))))
    log = CerLog(jsonl_path=None)
    log.observe(
        {
            "video_clock_ns": 5_000_000_000,
            "frame_seq": 3,
            "coupling": 0.4,
            "controller_bodied": True,
        }
    )
    clock.flush(timeout_s=2.0)
    rec = clock.last() or (recent_receipts(1)[-1] if recent_receipts(1) else None)
    assert rec is not None
    assert rec["schema_version"] == RECEIPT_SCHEMA
    assert rec["kind"] == "haptic_receipt_dark"
    assert seen == []
    bus.close()


def test_start_receipt_from_env_writes_private_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_HAPTIC_RECEIPT", "1")
    clock = start_receipt_clock(session_id="envr", out_dir=tmp_path)
    try:
        assert clock.persist is True
        assert clock._jsonl is not None
        assert "receipt" in clock._jsonl.name
        clock.note_tick(_tick(bodied=False, ticket=""))
        clock.flush(timeout_s=2.0)
        assert clock.last() is not None
        assert clock.last()["public_surfaces"] is False
    finally:
        reset_receipt_clock()
