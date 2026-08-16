"""Optical title-presence — FSM, plane field, fail-closed, incumbent OFF path."""

from __future__ import annotations

from qoresence.core.types import EventType
from qoresence.core.unified_config import GameDetectionConfig, GameProfileId
from qoresence.game_detection import GameAutoDetector, GameDetectionResult
from qoresence.vision.title_presence import (
    PLANE,
    claim_record,
    is_overlay_state,
    no_claim_record,
    record_valid,
    step_hysteresis,
    title_family_for,
)


def test_plane_hard_on_claim_and_no_claim():
    rec = no_claim_record(
        session_id="s", clock_ns=1, session_head_ns=0, reason="below_threshold"
    )
    assert rec["plane"] == PLANE
    assert rec["claim"] is False
    assert rec["profile_id"] is None
    assert "score" not in rec
    assert record_valid(rec)
    locked = claim_record(
        session_id="s",
        clock_ns=2,
        session_head_ns=0,
        profile_id="madden_27",
        display_name="EA Sports Madden NFL 27",
        confidence=0.9,
        threshold=0.65,
        consecutive=2,
        stability_count=2,
        evidence_count=3,
        vlm_confidence=0.8,
        ocr_confidence=0.7,
        motion_confidence=0.1,
    )
    assert locked["plane"] == PLANE
    assert locked["claim"] is True
    assert locked["title_family"] == "football"
    assert locked["profile_id"] == "madden_27"
    assert "home_score" not in locked
    assert "player" not in locked


def test_fsm_transitions():
    assert step_hysteresis(
        has_frame=False, confidence=0.9, threshold=0.65, consecutive=0,
        stability_count=2, overlay=False, profile_changed=False,
    )[0] == "unknown"
    assert step_hysteresis(
        has_frame=True, confidence=0.4, threshold=0.65, consecutive=0,
        stability_count=2, overlay=False, profile_changed=False,
    ) == ("unknown", "below_threshold")
    assert step_hysteresis(
        has_frame=True, confidence=0.9, threshold=0.65, consecutive=1,
        stability_count=2, overlay=False, profile_changed=False,
    ) == ("transitioning", "not_locked")
    assert step_hysteresis(
        has_frame=True, confidence=0.9, threshold=0.65, consecutive=2,
        stability_count=2, overlay=False, profile_changed=False,
    ) == ("locked", None)
    assert step_hysteresis(
        has_frame=True, confidence=0.9, threshold=0.65, consecutive=2,
        stability_count=2, overlay=True, profile_changed=False,
    ) == ("overlay-rejected", "overlay_rejected")


def test_overlay_menu_and_huddle_gameplay():
    assert is_overlay_state("menu") is True
    assert is_overlay_state("gameplay") is False
    assert is_overlay_state("unknown") is False
    # locked board + down/quarter → effective gameplay (huddle)
    assert is_overlay_state("menu", locked_board=True, quarter=1, down=2) is False


def test_title_family_cfb_madden():
    assert title_family_for("ncaa_football_27") == "football"
    assert title_family_for("madden_27") == "football"
    assert title_family_for("call_of_duty") == "shooter"


def test_config_title_presence_default_off():
    assert GameDetectionConfig().title_presence is False
    assert GameDetectionConfig().enabled is False


def test_event_type_exists():
    assert EventType.TITLE_PRESENCE.value == "title_presence"
    assert EventType.GAME_DETECTED.value == "game_detected"


class _Bus:
    session_id = "sid-test"

    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit_raw(self, **kwargs):
        self.events.append(kwargs)
        return True


def _result(profile=GameProfileId.MADDEN_27, conf=0.9) -> GameDetectionResult:
    return GameDetectionResult(
        profile_id=profile,
        display_name="EA Sports Madden NFL 27",
        confidence=conf,
        evidence_count=2,
        vlm_confidence=0.8,
        ocr_confidence=0.7,
        motion_confidence=0.1,
        timestamp_ns=1,
    )


def test_incumbent_off_emits_without_plane():
    bus = _Bus()
    det = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=False, stability_count=2
    )
    det._maybe_emit_and_switch(_result())
    det._maybe_emit_and_switch(_result())
    types = [e["event_type"] for e in bus.events]
    assert EventType.GAME_DETECTED in types or any(
        getattr(t, "value", t) == "game_detected" for t in types
    )
    gd = [e for e in bus.events if str(getattr(e["event_type"], "value", e["event_type"])) == "game_detected"]
    assert gd
    assert "plane" not in gd[0]["payload"]
    assert not any(
        str(getattr(e["event_type"], "value", e["event_type"])) == "title_presence" for e in bus.events
    )


def test_title_presence_on_gates_and_tags_plane():
    bus = _Bus()
    det = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=True, stability_count=2
    )
    det._maybe_emit_and_switch(_result())
    kinds = [str(getattr(e["event_type"], "value", e["event_type"])) for e in bus.events]
    assert "game_detected" not in kinds
    assert "title_presence" in kinds
    assert bus.events[0]["payload"]["plane"] == PLANE
    assert bus.events[0]["payload"]["claim"] is False
    det._maybe_emit_and_switch(_result())
    kinds = [str(getattr(e["event_type"], "value", e["event_type"])) for e in bus.events]
    assert "game_detected" in kinds
    gd = [e for e in bus.events if str(getattr(e["event_type"], "value", e["event_type"])) == "game_detected"][-1]
    assert gd["payload"]["plane"] == PLANE
    rec = gd["payload"]["title_presence"]
    assert rec["plane"] == PLANE
    assert rec["claim"] is True
    assert rec["profile_id"] == "madden_27"
    assert "home_score" not in rec
    assert rec.get("no_claim_reason") is None


def test_low_confidence_is_no_claim():
    bus = _Bus()
    det = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=True, stability_count=2
    )
    det._maybe_emit_and_switch(_result(conf=0.2))
    det._maybe_emit_and_switch(_result(conf=0.2))
    kinds = [str(getattr(e["event_type"], "value", e["event_type"])) for e in bus.events]
    assert "game_detected" not in kinds
    tp = [e for e in bus.events if str(getattr(e["event_type"], "value", e["event_type"])) == "title_presence"]
    assert tp
    assert tp[0]["payload"]["claim"] is False
    assert tp[0]["payload"]["profile_id"] is None


def test_overlay_rejects_claim():
    bus = _Bus()
    det = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=True, stability_count=1
    )
    det._last_game_state = "menu"
    det._maybe_emit_and_switch(_result())
    kinds = [str(getattr(e["event_type"], "value", e["event_type"])) for e in bus.events]
    assert "game_detected" not in kinds
    assert bus.events[-1]["payload"]["hysteresis_state"] == "overlay-rejected"
    assert bus.events[-1]["payload"]["claim"] is False
