"""Clock-licensed actuators — registry + four receipts (Phase 2)."""

from __future__ import annotations

from qoresence.agents.actuators import (
    KNOWN_ACTUATORS,
    aperture_from_video,
    arm_from_policy,
    bind_from_sync,
    evaluate_actuators,
    license_from_tickets,
    registry,
)


def test_registry_names_the_four_actuators():
    rows = registry()
    names = [r["name"] for r in rows]
    assert names == list(KNOWN_ACTUATORS)
    for row in rows:
        assert "inputs" in row and "outputs" in row
        assert row["path"] in {"fast", "confirm"}
        assert "requires_ticket" in row


def test_aperture_live_when_age_fresh():
    rec = aperture_from_video(
        {"age_s": 0.08, "has_frame": True, "frames": 1200, "pushes": 1190},
        clock_ns=11,
        frame_seq=9,
    )
    assert rec.actuator == "aperture"
    assert rec.kind == "live"
    assert rec.clock_ns == 11
    assert rec.frame_seq == 9
    assert rec.path == "fast"


def test_aperture_freeze_when_age_climbs():
    rec = aperture_from_video({"age_s": 6.2, "has_frame": True, "frames": 40})
    assert rec.kind == "freeze"
    assert "age" in rec.text.lower() or "freeze" in rec.text.lower()


def test_bind_reports_pll_and_lag():
    rec = bind_from_sync(
        {"pll_lock": True, "binds": 4, "lag_center_ms": 48, "sync_lag_ms": 48}
    )
    assert rec.actuator == "bind"
    assert rec.kind == "lock"
    assert rec.evidence.get("pll_lock") is True


def test_bind_open_when_pll_false():
    rec = bind_from_sync({"pll_lock": False, "binds": 0, "lag_center_ms": 180})
    assert rec.kind == "open"


def test_license_veto_without_ticket():
    rec = license_from_tickets(coupling_ticket_id="", confirm_ticket_id="", score_vlm_locked=False)
    assert rec.actuator == "license"
    assert rec.kind == "veto"
    assert not rec.ticket_id


def test_license_live_with_coupling_ticket():
    rec = license_from_tickets(coupling_ticket_id="c-1", confirm_ticket_id="", score_vlm_locked=False)
    assert rec.kind == "ticket"
    assert rec.ticket_id == "c-1"
    assert rec.path == "fast"


def test_arm_hold_without_policy():
    rec = arm_from_policy(climax=0.1, locked_score_delta=False, operator_post=False)
    assert rec.actuator == "arm"
    assert rec.kind == "hold"


def test_arm_clip_on_climax():
    rec = arm_from_policy(climax=0.8, locked_score_delta=False, operator_post=False)
    assert rec.kind == "clip"


def test_evaluate_returns_one_receipt_per_actuator():
    rows = evaluate_actuators(
        {
            "video": {"age_s": 0.05, "has_frame": True, "frames": 10},
            "coupling": {"pll_lock": False, "binds": 0},
            "situation": {},
        }
    )
    assert [r.actuator for r in rows] == list(KNOWN_ACTUATORS)
    blob = {r.actuator: r.to_dict() for r in rows}
    assert blob["aperture"]["kind"] == "live"
    assert blob["license"]["kind"] == "veto"
