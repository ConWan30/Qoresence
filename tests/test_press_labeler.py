"""Press labeler — labeled / unlabeled / eaten, never a fourth outcome."""

from __future__ import annotations

import time

from qoresence.core.unified_config import JevConfig, RetinaUnifiedConfig
from qoresence.observability.press_labeler import (
    PressLabeler,
    compose_press_label,
    local_press_labels,
    make_press_labeler_from_config,
)


def test_labeler_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.jev.enabled is False
    assert make_press_labeler_from_config(config.jev) is None


def test_sheet_verb_labels():
    out = compose_press_label(
        hid_button="Cross",
        frame_seq=42,
        clock_ns=100,
        verb="Snap Ball",
        mode="preplay_offense",
        efficacy_noul=0.9,
    )
    assert out["outcome"] == "labeled"
    assert out["label"] == "Snap Ball"
    assert out["label_source"] == "sheet"
    assert out["licenses_digits"] is False


def test_no_verb_is_unlabeled_not_invented():
    out = compose_press_label(
        hid_button="Triangle",
        verb=None,
        mode=None,
        efficacy_noul=0.5,
    )
    assert out["outcome"] == "unlabeled"
    assert out["label"] is None
    assert out["gamer"] == ""


def test_eaten_when_picture_does_not_respond():
    out = compose_press_label(
        hid_button="Cross",
        verb="Snap Ball",
        mode="preplay_offense",
        efficacy_noul=0.15,
        has_after_evidence=True,
    )
    assert out["outcome"] == "eaten"
    assert "no picture response" in out["gamer"]


def test_eaten_requires_after_evidence():
    out = compose_press_label(
        hid_button="Cross",
        verb="Snap Ball",
        mode="preplay_offense",
        efficacy_noul=0.1,
    )
    assert out["outcome"] == "labeled"  # no after-state → not eaten
    out = compose_press_label(
        hid_button="R2",
        verb=None,
        efficacy_noul=0.1,
    )
    assert out["outcome"] == "unlabeled"  # missing evidence is not negative evidence


def test_jev_picked_mode_labels_via_sheet_verb():
    out = compose_press_label(
        hid_button="Cross",
        verb=None,
        mode=None,
        picked_mode="preplay_offense",
        picked_verb="Snap Ball",
        mode_confidence=0.8,
        efficacy_noul=0.8,
    )
    assert out["outcome"] == "labeled"
    assert out["label"] == "Snap Ball"
    assert out["label_source"] == "jev_mode_pick"


def test_coin_flip_efficacy_is_not_eaten():
    out = compose_press_label(hid_button="R2", verb=None, efficacy_noul=0.45)
    assert out["outcome"] == "unlabeled"


def test_conflict_lag_beats_eaten():
    out = compose_press_label(
        hid_button="Cross",
        verb="Snap Ball",
        mode="preplay_offense",
        efficacy_noul=0.1,
        has_after_evidence=True,
        conflict={"picture_sheet": "running", "pad_sheet": "preplay_offense", "kind": "lag"},
        conflict_pick="lag",
        conflict_confidence=0.9,
    )
    assert out["outcome"] == "labeled"
    assert out["conflict_resolution"] == "lag"


def test_heuristic_never_upgrades_unlabeled():
    out = local_press_labels(
        {
            "obs": {"verb": None, "mode": None},
            "picture": {"phase_before": "preplay", "phase_after": "pass_play"},
        }
    )
    assert out["mode_pick"] == "no_match"
    assert out["efficacy_noul"] >= 0.6


def test_heuristic_same_phase_is_eaten_signal():
    out = local_press_labels(
        {
            "obs": {"verb": "Snap Ball", "mode": "preplay_offense"},
            "picture": {"phase_before": "preplay", "phase_after": "preplay"},
        }
    )
    assert out["efficacy_noul"] <= 0.3


def test_labeler_off_returns_deterministic():
    lab = PressLabeler(JevConfig(enabled=False))
    out = lab.label_press(
        {"hid_button": "Cross", "verb": "Snap Ball", "mode": "preplay_offense", "frame_seq": 1}
    )
    assert out["outcome"] == "labeled"
    assert out["source"] != "typesafe"


def test_labeler_enabled_uses_ask_fn():
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=lambda s: {
            "mode_pick": "preplay_offense",
            "mode_confidence": 0.85,
            "efficacy_noul": 0.8,
            "source": "fake",
        },
    )

    class _Lookup:
        def lookup_verb(self, button, mode):
            return "Snap Ball" if (button, mode) == ("Cross", "preplay_offense") else None

    out = lab.label_press(
        {"hid_button": "Cross", "verb": None, "mode": None, "frame_seq": 7},
        context={"candidate_modes": ["preplay_offense", "running"], "phase_before": "preplay", "phase_after": "pass_play"},
        lookup=_Lookup(),
    )
    assert out["outcome"] == "labeled"
    assert out["label"] == "Snap Ball"
    assert out["label_source"] == "jev_mode_pick"
    assert out["source"] == "fake"
    stats = lab.stats()
    assert stats["labeled"] == 1


def test_labeler_rejects_mode_outside_candidates():
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=lambda s: {
            "mode_pick": "made_up_mode",
            "mode_confidence": 0.99,
            "efficacy_noul": 0.8,
            "source": "fake",
        },
    )
    out = lab.label_press(
        {"hid_button": "Cross", "verb": None, "mode": None},
        context={"candidate_modes": ["preplay_offense"]},
        lookup=None,
    )
    assert out["outcome"] == "unlabeled"
    assert out["label"] is None


def test_preflight_skips_model_when_deterministic():
    called = []
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=lambda s: called.append(s) or {},
    )
    out = lab.label_press(
        {"hid_button": "Cross", "verb": "Snap Ball", "mode": "preplay_offense", "frame_seq": 3},
        context={"candidate_modes": ["preplay_offense"]},
    )
    assert called == []
    assert out["outcome"] == "labeled"
    assert out["label"] == "Snap Ball"
    assert out["source"] == "preflight"
    assert lab.stats()["labeled"] == 1


def test_preflight_does_not_skip_when_phase_after_present():
    called = []
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=lambda s: called.append(s) or {
            "mode_pick": "no_match",
            "efficacy_noul": 0.15,
            "source": "fake",
        },
    )
    out = lab.label_press(
        {"hid_button": "Cross", "verb": "Snap Ball", "mode": "preplay_offense", "frame_seq": 3},
        context={
            "candidate_modes": ["preplay_offense"],
            "phase_before": "preplay",
            "phase_after": "preplay",
        },
    )
    assert len(called) == 1
    assert out["outcome"] == "eaten"


# ── Post-press verdicts (after-evidence sampling) ─────────────────────────


def _ctx(phase):
    """Stand-in VisualContext — fresh object each call, like the lobe emits."""
    return {"details": {"visual_phase": phase}, "latency_ms": 0}


def _efficacy_ask(state):
    pic = state["picture"]
    after = pic.get("phase_after")
    eff = 0.2 if (after is not None and after == pic.get("phase_before")) else 0.75
    return {"mode_pick": "no_match", "efficacy_noul": eff, "source": "fake"}


def _wait_verdict(lab, timeout_s=2.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        got = lab.drain_verdicts()
        if got:
            return got[-1]
        time.sleep(0.02)
    return None


def test_verdict_eaten_when_after_phase_unchanged():
    holder = {"ctx": _ctx("preplay")}
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=_efficacy_ask,
        context_fn=lambda: holder["ctx"],
        after_delay_s=0.05,
        after_timeout_s=1.0,
        after_poll_s=0.01,
    )
    try:
        out = lab.label_press(
            {"hid_button": "Cross", "verb": None, "mode": None, "frame_seq": 5, "clock_ns": 10},
            context={"visual_phase": "preplay"},
        )
        assert out["outcome"] == "unlabeled"
        # Fresh context lands post-window with the same phase → real non-response.
        # (Swapped in only after the response window closed — a context that
        # arrives *inside* the window is correctly rejected as too-early.)
        time.sleep(0.15)
        holder["ctx"] = _ctx("preplay")
        verdict = _wait_verdict(lab)
        assert verdict is not None
        assert verdict["verdict"] is True
        assert verdict["outcome"] == "eaten"
        assert verdict["phase_after"] == "preplay"
        assert verdict["provisional"]["outcome"] == "unlabeled"
        stats = lab.stats()
        assert stats["after"]["sampled"] == 1
        assert stats["verdicts"]["eaten"] == 1
    finally:
        lab.stop()


def test_verdict_flips_sheet_label_to_eaten():
    holder = {"ctx": _ctx("huddle_offense")}
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=_efficacy_ask,
        context_fn=lambda: holder["ctx"],
        after_delay_s=0.05,
        after_timeout_s=1.0,
        after_poll_s=0.01,
    )
    try:
        out = lab.label_press(
            {
                "hid_button": "Cross",
                "verb": "Snap Ball",
                "mode": "preplay_offense",
                "frame_seq": 5,
                "clock_ns": 10,
            },
            context={"visual_phase": "huddle_offense"},
        )
        assert out["outcome"] == "labeled"
        assert out["source"] == "preflight"
        time.sleep(0.15)
        holder["ctx"] = _ctx("huddle_offense")
        verdict = _wait_verdict(lab)
        assert verdict is not None
        assert verdict["outcome"] == "eaten"
        assert verdict["provisional"]["outcome"] == "labeled"
    finally:
        lab.stop()


def test_verdict_responded_when_phase_advances():
    holder = {"ctx": _ctx("huddle_offense")}
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=_efficacy_ask,
        context_fn=lambda: holder["ctx"],
        after_delay_s=0.05,
        after_timeout_s=1.0,
        after_poll_s=0.01,
    )
    try:
        lab.label_press(
            {
                "hid_button": "Cross",
                "verb": "Snap Ball",
                "mode": "preplay_offense",
                "frame_seq": 5,
                "clock_ns": 10,
            },
            context={"visual_phase": "huddle_offense"},
        )
        time.sleep(0.15)
        holder["ctx"] = _ctx("running")
        verdict = _wait_verdict(lab)
        assert verdict is not None
        assert verdict["outcome"] == "labeled"
        assert verdict["responded"] is True
        assert verdict["phase_after"] == "running"
    finally:
        lab.stop()


def test_verdict_timeout_keeps_provisional():
    ctx = _ctx("preplay")  # same object forever — never "fresh"
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=_efficacy_ask,
        context_fn=lambda: ctx,
        after_delay_s=0.02,
        after_timeout_s=0.15,
        after_poll_s=0.01,
    )
    try:
        out = lab.label_press(
            {"hid_button": "Cross", "verb": None, "mode": None, "frame_seq": 5, "clock_ns": 10}
        )
        assert out["outcome"] == "unlabeled"
        verdict = _wait_verdict(lab)
        assert verdict is not None
        assert verdict["after_timeout"] is True
        assert verdict["phase_after"] is None
        assert verdict["outcome"] == "unlabeled"  # no evidence either way
        stats = lab.stats()
        assert stats["after"]["timeout"] == 1
    finally:
        lab.stop()


def test_verdicts_ride_next_wire():
    import qoresence.observability.press_labeler as pl_mod

    holder = {"ctx": _ctx("preplay")}
    lab = PressLabeler(
        JevConfig(enabled=True),
        ask_fn=_efficacy_ask,
        context_fn=lambda: holder["ctx"],
        after_delay_s=0.05,
        after_timeout_s=1.0,
        after_poll_s=0.01,
    )
    saved = pl_mod._singleton
    pl_mod._singleton = lab
    try:
        wire1 = {
            "hid_button": "Cross",
            "frame_seq": 1,
            "clock_ns": 1,
            "game_profile": "madden_27",
            "visual_phase": "preplay",
        }
        plabel1 = pl_mod.label_wire_press(wire1)
        assert plabel1["outcome"] == "unlabeled"
        assert "press_verdicts" not in wire1
        time.sleep(0.15)
        holder["ctx"] = _ctx("preplay")
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and lab.stats()["verdicts"]["total"] < 1:
            time.sleep(0.02)
        wire2 = {
            "hid_button": "Square",
            "frame_seq": 40,
            "clock_ns": 2,
            "game_profile": "madden_27",
        }
        pl_mod.label_wire_press(wire2)
        assert wire2["press_verdicts"][0]["outcome"] == "eaten"
    finally:
        pl_mod._singleton = saved
        lab.stop()
