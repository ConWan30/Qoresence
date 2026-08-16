"""Two-speed FastMomentEngine unit tests (no hardware)."""

from __future__ import annotations

from qoresence.agents.fast_moment import FastMomentEngine, soft_chat_has_score_digits
from qoresence.agents.situation_model import SituationState


def _red_zone_state(**kw) -> SituationState:
    s = SituationState(
        game_state="gameplay",
        game_category="football",
        game_profile="ncaa_football_27",
        field_position="opp 12",
        quarter=4,
        home_score=14,
        away_score=10,
        down=1,
        yards_to_go=10,
    )
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_fast_soft_chat_no_score_digits():
    eng = FastMomentEngine(chat_cooldown_s=0.0)
    moments = eng.score_fast(
        _red_zone_state(),
        coupling={"coupling": 0.7, "input_energy": 3.0, "buttons": ["r2"], "frame_seq": 42},
        features={"chat", "clip"},
    )
    chats = [m for m in moments if m.action == "chat" and m.triggered]
    assert chats, "expected soft chat on red-zone + high coupling"
    for m in chats:
        assert m.payload.get("path") == "fast"
        assert m.payload.get("factual") is False
        assert not soft_chat_has_score_digits(m.message)
        assert "14" not in m.message and "10" not in m.message


def test_fast_quiet_without_coupling():
    eng = FastMomentEngine()
    moments = eng.score_fast(
        _red_zone_state(),
        coupling={"coupling": 0.0, "input_energy": 0.0, "buttons": []},
        features={"chat", "clip"},
    )
    assert moments == []


def test_fast_clip_intent_on_high_coupling_red_zone():
    eng = FastMomentEngine(clip_cooldown_s=0.0, chat_cooldown_s=0.0)
    moments = eng.score_fast(
        _red_zone_state(),
        coupling={"coupling": 0.8, "input_energy": 5.0, "frame_seq": 9},
        features={"chat", "clip"},
    )
    clips = [m for m in moments if m.action == "clip" and m.triggered]
    assert clips
    assert clips[0].payload.get("path") == "fast"


def test_arm_prediction_and_clear_on_confirm():
    eng = FastMomentEngine(arm_cooldown_s=0.0, chat_cooldown_s=0.0, clip_cooldown_s=0.0)
    moments = eng.score_fast(
        _red_zone_state(),
        coupling={"coupling": 0.9, "input_energy": 4.0},
        features={"chat", "clip", "prediction"},
    )
    arms = [m for m in moments if m.action == "arm_prediction"]
    assert arms
    assert eng.prediction_armed() is True
    eng.on_confirm_score()
    assert eng.prediction_armed() is False


def test_input_spike_requires_coupling_ticket():
    from qoresence.sync.coupling_ticket import reset_coupling_book

    reset_coupling_book()
    eng = FastMomentEngine(chat_cooldown_s=0.0)
    # Gameplay, not red/close/late → would be input_spike, but no ticket
    sit = SituationState(
        game_state="gameplay",
        game_category="football",
        game_profile="ncaa_football_27",
        quarter=2,
        home_score=14,
        away_score=0,
    )
    moments = eng.score_fast(
        sit,
        coupling={"coupling": 0.7, "input_energy": 3.0, "buttons": ["r2"]},
        features={"chat"},
    )
    assert moments == []


def test_sanitize_strips_scorelike_patterns():
    eng = FastMomentEngine()
    dirty = eng._sanitize_soft("Look at that 21-14 swing")
    assert not soft_chat_has_score_digits(dirty)
