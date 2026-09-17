"""Press labeler — labeled / unlabeled / eaten, never a fourth outcome."""

from __future__ import annotations

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
    )
    assert out["outcome"] == "eaten"
    assert "no picture response" in out["gamer"]


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
