"""Three-rail haptic receipt — fail-closed join of HID, HDMI lock, haptic-out."""

from __future__ import annotations

from qoresence.core.civif_tick import CoupledTickRecord, SituationSnapshot
from qoresence.sync.haptic_receipt import (
    RECEIPT_SCHEMA,
    build_receipt,
    receipt_from_tick_and_obs,
    validate_receipt,
)
from qoresence.sync.haptic_schema import HAPTIC_PLANE, empty_record


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
