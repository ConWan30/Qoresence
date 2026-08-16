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


def test_lock_verify_mailbox_and_note():
    from qoresence.vision.title_presence import lock_verify_active, request_lock_verify

    request_lock_verify("phrase_sprint", window_s=2.0)
    on, why = lock_verify_active()
    assert on is True
    assert why == "phrase_sprint"
    bus = _Bus()
    det = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=True
    )
    det.note_lock_verify("title_flip", window_s=3.0)
    assert det._sampling_mode == "lock_verify"
    det_off = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=False
    )
    det_off.note_lock_verify("title_flip")
    assert det_off._sampling_mode == "sparse"


def test_wrap_ceremony_fail_closed():
    from qoresence.vision.title_presence_wrap import (
        OperatorGrant,
        WrapEnvelope,
        WrapRefuse,
        wrap_observation_for_plane,
    )

    rec = claim_record(
        session_id="s",
        clock_ns=1,
        session_head_ns=0,
        profile_id="madden_27",
        display_name="M",
        confidence=0.9,
        threshold=0.65,
        consecutive=2,
        stability_count=2,
        evidence_count=1,
        vlm_confidence=0.8,
        ocr_confidence=0.7,
        motion_confidence=0.1,
    )
    original = dict(rec)
    refused = wrap_observation_for_plane(rec, "qortroller-truth")
    assert isinstance(refused, WrapRefuse)
    assert refused.reason == "dest_denied"
    assert rec == original
    still_denied = wrap_observation_for_plane(
        rec,
        "qortroller-truth",
        OperatorGrant(grant_id="g0", dest_plane="qortroller-truth", expires_ns=10**18),
        allowlist={"qortroller-truth"},
        now_ns=1,
    )
    assert still_denied.reason == "dest_denied"
    grant = OperatorGrant(grant_id="g1", dest_plane="other-plane", expires_ns=10**18)
    still = wrap_observation_for_plane(rec, "other-plane", grant)
    assert isinstance(still, WrapRefuse)
    ok = wrap_observation_for_plane(
        rec, "other-plane", grant, allowlist={"other-plane"}, now_ns=1
    )
    assert isinstance(ok, WrapEnvelope)
    assert ok.plane == "other-plane"
    assert ok.source_plane == PLANE
    assert ok.source_hash
    assert rec["plane"] == PLANE
    no_claim = no_claim_record(session_id="s", clock_ns=1, session_head_ns=0, reason="not_locked")
    assert wrap_observation_for_plane(
        no_claim, "other-plane", grant, allowlist={"other-plane"}
    ).reason == "no_claim"
    live = wrap_observation_for_plane(
        rec,
        "qoresence-research",
        OperatorGrant(grant_id="g-research", dest_plane="qoresence-research", expires_ns=10**18),
        now_ns=1,
    )
    assert isinstance(live, WrapEnvelope)
    assert live.plane == "qoresence-research"


def test_research_ceremony_links_ingredient_without_mutating():
    from qoresence.vision.title_presence import source_hash
    from qoresence.vision.title_presence_ceremony import run_research_ceremony
    from qoresence.vision.title_presence_wrap import OperatorGrant

    rec = claim_record(
        session_id="s",
        clock_ns=1,
        session_head_ns=0,
        profile_id="madden_27",
        display_name="M",
        confidence=0.9,
        threshold=0.65,
        consecutive=2,
        stability_count=2,
        evidence_count=1,
        vlm_confidence=0.8,
        ocr_confidence=0.7,
        motion_confidence=0.1,
    )
    original = dict(rec)
    out = run_research_ceremony(
        rec,
        grant=OperatorGrant(
            grant_id="g-research", dest_plane="qoresence-research", expires_ns=10**18
        ),
        now_ns=5,
        persist=False,
    )
    assert out["ok"] is True
    assert rec == original
    assert out["wrap"]["source_hash"] == source_hash(rec)
    assert out["ingredient"]["source_hash"] == source_hash(rec)
    assert out["ingredient"]["dest_plane"] == "qoresence-research"
    denied = run_research_ceremony(
        rec,
        dest_plane="qortroller-truth",
        grant=OperatorGrant(grant_id="x", dest_plane="qortroller-truth", expires_ns=10**18),
        persist=False,
    )
    assert denied["ok"] is False
    assert denied["reason"] == "dest_denied"


def test_ingredient_immutable_and_decays():
    from qoresence.vision.title_presence import source_hash
    from qoresence.vision.title_presence_ingredient import decayed_confidence, make_ingredient

    rec = claim_record(
        session_id="s",
        clock_ns=100,
        session_head_ns=0,
        profile_id="ncaa_football_27",
        display_name="CFB",
        confidence=0.8,
        threshold=0.65,
        consecutive=2,
        stability_count=2,
        evidence_count=1,
        vlm_confidence=0.8,
        ocr_confidence=0.7,
        motion_confidence=0.1,
    )
    before = dict(rec)
    ing = make_ingredient(rec, created_ns=0, half_life_s=3600.0)
    assert ing is not None
    assert rec == before
    assert ing["source_hash"] == source_hash(rec)
    assert "ingredient" not in rec
    assert decayed_confidence(ing, 0) == 0.8
    later = decayed_confidence(ing, int(3600 * 1e9))
    assert abs(later - 0.4) < 1e-6


def test_situation_stays_in_sync_and_no_claim_does_not_wipe():
    from qoresence.agents.situation_model import SituationModel
    from qoresence.core.types import BaseEvent, EventType, SourceLobe

    sit = SituationModel()
    sit.seed_profile("madden_27")
    ev_nc = BaseEvent(
        session_id="s",
        clock_ns=1,
        source_lobe=SourceLobe.FUSION,
        type=EventType.TITLE_PRESENCE,
        payload=no_claim_record(session_id="s", clock_ns=1, session_head_ns=0, reason="not_locked"),
    )
    sit.update(ev_nc)
    assert sit.state.game_profile == "madden_27"
    assert sit.state.title_claim is False
    ev_ok = BaseEvent(
        session_id="s",
        clock_ns=2,
        source_lobe=SourceLobe.FUSION,
        type=EventType.TITLE_PRESENCE,
        payload=claim_record(
            session_id="s",
            clock_ns=2,
            session_head_ns=0,
            profile_id="madden_27",
            display_name="Madden",
            confidence=0.9,
            threshold=0.65,
            consecutive=2,
            stability_count=2,
            evidence_count=1,
            vlm_confidence=0.8,
            ocr_confidence=0.7,
            motion_confidence=0.1,
        ),
    )
    sit.update(ev_ok)
    assert sit.state.game_profile == "madden_27"
    assert sit.state.title_claim is True
    assert sit.state.title_hysteresis == "locked"
    d = sit.to_dict()
    assert d["title_claim"] is True


def test_title_flip_requests_lock_verify():
    bus = _Bus()
    det = GameAutoDetector(
        bus, 0, vlm_client=None, use_vision_stack=False, title_presence=True, stability_count=1
    )
    det._maybe_emit_and_switch(_result(GameProfileId.MADDEN_27))
    det._maybe_emit_and_switch(_result(GameProfileId.NCAA_FOOTBALL_27))
    assert det._sampling_mode == "lock_verify"
