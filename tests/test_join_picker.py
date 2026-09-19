"""Join picker — observation plane, fail-closed.

Selects an already-stamped hid_seq_line slot. Never licenses digits, never
writes lag_center, never interpolates HID[now].
"""

from __future__ import annotations

import time

from qoresence.core.unified_config import JoinPickerConfig, RetinaUnifiedConfig
from qoresence.observability.join_picker import (
    JoinPickerSentinel,
    build_candidates,
    compose_join_verdict,
    local_join_answers,
    make_join_picker_from_config,
    slot_from_sample,
)
from qoresence.sync.hid_seq_line import HidSeqSample


def _sentinel(tmp_path, **kw):
    cfg = JoinPickerConfig(enabled=True, out_dir=str(tmp_path), cadence_s=0.05)
    return JoinPickerSentinel(cfg, **kw)


def _slot(*, seq=10, lag_ms=80.0, r2=0.8, lx=0.0, ly=0.0, l2=0.0, buttons=("r2",)):
    hub_ns = 1_000_000_000
    hid_ns = hub_ns - int(lag_ms * 1e6)
    return HidSeqSample(
        hub_seq=seq,
        hub_clock_ns=hub_ns,
        hid_clock_ns=hid_ns,
        lx=lx,
        ly=ly,
        r2=r2,
        l2=l2,
        buttons=buttons,
        hid_domain="usb_play",
    )


def _idle_sample(seq=10):
    return _slot(seq=seq, r2=0.0, lx=0.0, ly=0.0, l2=0.0, buttons=())


def test_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.join_picker.enabled is False
    assert make_join_picker_from_config(config.join_picker) is None


def test_umbrella_jev_enables():
    sen = make_join_picker_from_config(
        JoinPickerConfig(enabled=False),
        jev_enabled=True,
    )
    assert sen is not None
    assert sen.enabled is True
    sen.stop()


def test_compose_never_licenses_digits():
    cands = build_candidates({10: _slot(seq=10)}, 10)
    for action in ("stamp", "observe", "dark"):
        out = compose_join_verdict(
            join_id="now" if action != "dark" else "none",
            join_confidence=0.9 if action == "stamp" else 0.5,
            picture_answered=0.9 if action == "stamp" else (0.2 if action == "dark" else 0.5),
            join_honesty=2.0 if action == "stamp" else 1.0,
            candidates=cands,
        )
        assert out["licenses_digits"] is False
        assert out["plane"] == "qoresence-observation"


def test_none_when_all_slots_idle():
    cands = build_candidates(
        {8: _idle_sample(8), 9: _idle_sample(9), 10: _idle_sample(10)},
        10,
    )
    answers = local_join_answers(
        {"candidates": cands, "picture": {"visual_phase": "snap", "lag_center_ms": 80}}
    )
    out = compose_join_verdict(
        join_id=answers["join_id"],
        join_confidence=answers["join_confidence"],
        picture_answered=answers["picture_answered"],
        join_honesty=answers["join_honesty"],
        act_kind=answers["act_kind"],
        candidates=cands,
    )
    assert out["join_id"] == "none"
    assert out["action"] == "dark"


def test_picks_now_when_only_now_live():
    cands = build_candidates({10: _slot(seq=10, lag_ms=82, r2=0.9)}, 10)
    answers = local_join_answers(
        {
            "candidates": cands,
            "picture": {
                "visual_phase": "snap",
                "hud_kind": "live_hud",
                "game_state": "gameplay",
                "lag_center_ms": 80,
            },
        }
    )
    out = compose_join_verdict(
        join_id=answers["join_id"],
        join_confidence=answers["join_confidence"],
        picture_answered=answers["picture_answered"],
        join_honesty=answers["join_honesty"],
        act_kind=answers["act_kind"],
        candidates=cands,
    )
    assert answers["join_id"] == "now"
    assert out["action"] == "stamp"
    assert out["join_seq"] == 10


def test_picture_unanswered_forces_none():
    cands = build_candidates({10: _slot(seq=10, r2=0.9)}, 10)
    answers = local_join_answers(
        {
            "candidates": cands,
            "picture": {"hud_kind": "menu", "game_state": "menu", "lag_center_ms": 80},
        }
    )
    out = compose_join_verdict(
        join_id=answers["join_id"],
        join_confidence=answers["join_confidence"],
        picture_answered=answers["picture_answered"],
        join_honesty=answers["join_honesty"],
        act_kind=answers["act_kind"],
        candidates=cands,
    )
    assert out["join_id"] == "none"
    assert out["action"] == "dark"


def test_low_confidence_observe_not_stamp():
    cands = build_candidates({10: _slot(seq=10)}, 10)
    out = compose_join_verdict(
        join_id="now",
        join_confidence=0.45,
        picture_answered=0.8,
        join_honesty=1.0,
        candidates=cands,
    )
    assert out["action"] == "observe"
    assert out["join_id"] == "now"


def test_join_id_must_be_present_slot():
    cands = build_candidates({10: _slot(seq=10)}, 10)
    assert cands["ahead_1"]["present"] is False
    out = compose_join_verdict(
        join_id="ahead_1",
        join_confidence=0.95,
        picture_answered=0.95,
        join_honesty=2.0,
        candidates=cands,
    )
    assert out["join_id"] == "none"
    assert out["action"] == "dark"


def test_tick_does_not_call_system_one_on_construct(tmp_path):
    asked = {"n": 0}

    def _ask(state):
        asked["n"] += 1
        return local_join_answers(state)

    sen = _sentinel(
        tmp_path,
        ask_fn=_ask,
        candidates_fn=lambda seq: build_candidates({10: _slot(seq=10)}, 10),
        picture_fn=lambda: {"visual_phase": "snap", "hud_kind": "live_hud", "lag_center_ms": 80},
        hub_seq_fn=lambda: 10,
    )
    try:
        # Cadence wait happens first; construction must not ask inline.
        assert asked["n"] == 0
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        assert sen.stats()["judged"] >= 1
        assert sen.stats()["licenses_digits"] is False
    finally:
        sen.stop()


def test_never_writes_lag_center(monkeypatch):
    calls = {"n": 0}

    def _boom(*a, **k):
        calls["n"] += 1
        raise AssertionError("PLL must not be written by join picker")

    import qoresence.sync.lag_estimator as le

    monkeypatch.setattr(le.LagEstimator, "observe", _boom)
    monkeypatch.setattr(le.LagEstimator, "observe_phase", _boom)
    cands = build_candidates({10: _slot(seq=10)}, 10)
    local_join_answers(
        {"candidates": cands, "picture": {"visual_phase": "snap", "lag_center_ms": 80}}
    )
    assert calls["n"] == 0


def test_candidate_builder_uses_hid_seq_line_only(monkeypatch):
    def _pose_at(*a, **k):
        raise AssertionError("must not sample InputRing.now")

    import qoresence.sync.input_ring as ir

    monkeypatch.setattr(ir.InputRing, "pose_at", _pose_at, raising=False)
    samples = {9: _slot(seq=9, lag_ms=120), 10: _slot(seq=10, lag_ms=80)}
    cands = build_candidates(samples, 10)
    assert cands["now"]["present"] is True
    assert cands["behind_1"]["present"] is True
    assert cands["behind_2"]["present"] is False
    assert cands["ahead_1"]["present"] is False
    assert slot_from_sample(None)["present"] is False
