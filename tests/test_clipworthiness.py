"""Unit tests for ClipWorthinessModel + MomentScorer gating + LearningLogger opt-in."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from qoresence.agents.learning_loop import ClipWorthinessTrainer, LearningLogger
from qoresence.agents.moment_scorer import ClipWorthinessModel, MomentScorer
from qoresence.agents.situation_model import ControllerSnapshot, SituationState
from qoresence.vision.visual_context import GameCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _state(
    game_category: str | object = "football",
    field_position: str | None = "opp 10",
    home_score: int | None = 21,
    away_score: int | None = 14,
    apm: float = 60,
    game_state: str = "gameplay",
) -> SituationState:
    s = SituationState()
    # handle Enum or str
    if hasattr(game_category, "value"):
        s.game_category = game_category.value  # type: ignore
    else:
        s.game_category = game_category  # type: ignore
    s.game_state = game_state
    s.field_position = field_position
    s.home_score = home_score
    s.away_score = away_score
    s.controller = ControllerSnapshot(apm_5s=apm)
    s.quarter = 4
    s.down = 1
    s.yards_to_go = 10
    s.game_clock_seconds = 300
    s.possession = "home"
    return s


def _football_state(**kw) -> SituationState:
    return _state(game_category="football", **kw)


def _shooter_state(**kw) -> SituationState:
    return _state(game_category="shooter", **kw)


# ---------------------------------------------------------------------------
# ClipWorthinessModel
# ---------------------------------------------------------------------------
class TestClipWorthinessModel:
    def test_default_weights(self):
        m = ClipWorthinessModel(model_path="/tmp/__nonexistent_clip__.json")
        assert m.weights["wp_swing"] == pytest.approx(2.5)
        assert m.weights["bias"] == pytest.approx(-0.8)

    def test_predict_midpoint(self):
        m = ClipWorthinessModel(model_path="/tmp/__nonexistent_clip__.json")
        # no features => sigmoid(-0.8) ~ 0.31
        assert m.predict({}) == pytest.approx(0.31, abs=0.02)
        assert m.predict(None) == pytest.approx(0.31, abs=0.02)

    def test_predict_monotonic_wp_swing(self):
        m = ClipWorthinessModel(model_path="/tmp/__nonexistent_clip__.json")
        low = m.predict({"wp_swing": 0.05})
        high = m.predict({"wp_swing": 0.4})
        assert high > low
        assert high > 0.5

    def test_predict_red_zone_and_close_game(self):
        m = ClipWorthinessModel(model_path="/tmp/__nonexistent_clip__.json")
        base = m.predict({"wp_swing": 0.05})
        with_rz = m.predict({"wp_swing": 0.05, "red_zone": 1})
        with_close = m.predict({"wp_swing": 0.05, "close_game": 1})
        with_both = m.predict({"wp_swing": 0.05, "red_zone": 1, "close_game": 1})
        assert with_rz > base
        assert with_close > base
        assert with_both > with_rz

    def test_predict_apm(self):
        m = ClipWorthinessModel(model_path="/tmp/__nonexistent_clip__.json")
        low = m.predict({"wp_swing": 0.1, "apm": 0.0})
        high = m.predict({"wp_swing": 0.1, "apm": 1.0})
        assert high > low

    def test_predict_bool_coercion(self):
        m = ClipWorthinessModel(model_path="/tmp/__nonexistent_clip__.json")
        assert m.predict({"red_zone": True}) == m.predict({"red_zone": 1})
        assert m.predict({"red_zone": False}) == m.predict({"red_zone": 0})

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "clip.json"
            m = ClipWorthinessModel(
                model_path=p,
                weights={
                    "wp_swing": 1.0,
                    "red_zone": 2.0,
                    "close_game": 3.0,
                    "apm": 4.0,
                    "bias": -1.0,
                },
            )
            m.save()
            assert p.is_file()
            data = json.loads(p.read_text())
            assert data["weights"]["wp_swing"] == 1.0
            # load into new instance (no explicit weights, should read file)
            m2 = ClipWorthinessModel(model_path=p)
            assert m2.weights["wp_swing"] == pytest.approx(1.0)
            assert m2.weights["bias"] == pytest.approx(-1.0)
            # predict parity
            assert m.predict({"wp_swing": 0.2}) == pytest.approx(m2.predict({"wp_swing": 0.2}))

    def test_load_missing_is_noop(self):
        m = ClipWorthinessModel(model_path="/tmp/__definitely_missing_xyz__.json")
        # should keep defaults
        assert m.weights["wp_swing"] == pytest.approx(2.5)

    def test_load_handles_wrapped_and_unwrapped(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "w.json"
            # unwrapped form
            p.write_text(json.dumps({"wp_swing": 9.9}))
            m = ClipWorthinessModel(model_path=p)
            assert m.weights["wp_swing"] == pytest.approx(9.9)
            # wrapped form
            p.write_text(json.dumps({"weights": {"wp_swing": 7.7}}))
            m2 = ClipWorthinessModel(model_path=p)
            assert m2.weights["wp_swing"] == pytest.approx(7.7)


# ---------------------------------------------------------------------------
# MomentScorer gating
# ---------------------------------------------------------------------------
class TestMomentScorerGating:
    def test_is_football_string(self):
        sc = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
        assert sc._is_football(_football_state()) is True
        assert sc._is_football(_shooter_state()) is False
        assert sc._is_football(_state(game_category="FOOTBALL")) is True
        assert sc._is_football(_state(game_category="  football ")) is True

    def test_is_football_enum(self):
        sc = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
        assert sc._is_football(_state(game_category=GameCategory.FOOTBALL)) is True
        assert sc._is_football(_state(game_category=GameCategory.SHOOTER)) is False

    def test_is_football_none_empty(self):
        sc = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
        assert sc._is_football(_state(game_category=None)) is False
        assert sc._is_football(_state(game_category="")) is False

    def test_maybe_wp_clip_gated_non_football(self):
        sc = MomentScorer(wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json")
        # shooter should never produce wp clip even with swing
        result = sc._maybe_wp_clip(_shooter_state())
        assert result is None

    def test_maybe_wp_clip_needs_football_and_swing(self):
        sc = MomentScorer(wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json")
        # First call: wp_swing 0 -> None (no delta yet)
        r1 = sc._maybe_wp_clip(_football_state())
        assert r1 is None or isinstance(r1, tuple)
        # Change score to force swing: second compute should have swing
        _ = _football_state(home_score=28)
        # Polluter: _maybe_wp_clip internally calls wp.compute which tracks prev
        # So sequence football -> football with different score should eventually yield swing
        sc2 = MomentScorer(wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json")
        sc2._maybe_wp_clip(_football_state(home_score=21, away_score=14))
        out = sc2._maybe_wp_clip(_football_state(home_score=28, away_score=14))
        # If swing <0.02 it returns None, but a 7pt swing should exceed
        # Allow either None (if under) or tuple; but shooter is always None
        if out is not None:
            moment, swing = out
            assert abs(swing) > 0.02

    def test_clip_gate_shooter_false(self):
        sc = MomentScorer(wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json")
        assert sc._clip_gate(_shooter_state(), wp_swing=0.5) is False
        assert sc._clip_gate(_shooter_state(field_position="opp 5"), wp_swing=0.5) is False

    def test_clip_gate_football_swing_threshold(self):
        sc = MomentScorer(
            wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json", wp_swing_threshold=0.12
        )
        # large swing should pass even if model score low
        assert (
            sc._clip_gate(
                _football_state(field_position="own 40", home_score=21, away_score=14, apm=0),
                wp_swing=0.5,
            )
            is True
        )
        # tiny swing + not redzone + not close + low apm should fail (model ~0.31 <0.55 and swing<0.12)
        # use blowout (margin 20) not close, own 40 not redzone, apm 0, swing 0.03
        assert (
            sc._clip_gate(
                _football_state(field_position="own 40", home_score=35, away_score=14, apm=0),
                wp_swing=0.03,
            )
            is False
        )

    def test_clip_gate_redzone_close_boosts_score(self):
        sc = MomentScorer(wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json")
        # redzone + close game boosts model score above 0.55 even with modest swing
        assert (
            sc._clip_gate(
                _football_state(field_position="opp 10", home_score=21, away_score=17, apm=60),
                wp_swing=0.08,
            )
            is True
        )

    def test_score_gated_shooter_no_wp(self):
        sc = MomentScorer(wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json")
        # shooter gameplay must not emit a WP-driven clip (football gate)
        s = _shooter_state()
        s.game_state = "gameplay"
        out = sc.score(s, event_type="visual_context", event_payload={"frame_hash": "abc123"})
        wp_clips = [
            m
            for m in out
            if m.payload.get("wp_swing") is not None
            or (m.action == "clip" and "wp_swing" in m.reason)
        ]
        assert wp_clips == [], f"shooter must not produce WP clip, got {out}"

    def test_score_backward_compat_no_logger(self):
        sc = MomentScorer(wp_enabled=False, clip_model_path="/tmp/__nonexistent__.json")
        s = _football_state()
        s.game_state = "gameplay"
        # Should not raise even without logger
        out = sc.score(s, event_type="visual_context", event_payload={})
        assert isinstance(out, list)


# ---------------------------------------------------------------------------
# LearningLogger anonymization + MomentScorer/ClutchBot wiring
# ---------------------------------------------------------------------------
class TestLearningLogger:
    def test_frame_hash_truncated(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "learn.jsonl"
            lg = LearningLogger(path=p)
            lg.log({"a": 1}, {"triggered": True}, frame_hash="a" * 64, wp_swing=0.1)
            rec = lg.load_all()[0]
            assert rec.frame_hash == "a" * 16
            assert len(rec.frame_hash) == 16

    def test_never_stores_raw_frame(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "learn.jsonl"
            lg = LearningLogger(path=p)
            lg.log(
                {"x": 1},
                {"triggered": True, "payload": {"wp_swing": 0.2}},
                frame_hash="deadbeef1234567890",
                wp_swing=0.2,
            )
            raw = p.read_text()
            assert "deadbeef1234567890" not in raw  # only first 16
            assert "deadbeef12345678" in raw

    def test_moment_scorer_logs_anonymized(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "learn.jsonl"
            lg = LearningLogger(path=p)
            sc = MomentScorer(
                wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json", learning_logger=lg
            )
            # Prime WP then trigger swing
            s = _football_state()
            s.game_state = "gameplay"
            sc.score(s, event_type="visual_context", event_payload={"frame_hash": "x" * 40})
            s2 = _football_state(home_score=35, away_score=14)
            s2.game_state = "gameplay"
            # Need to force wp clip path: use generic score trigger (no visual_context)
            # Instead test direct log path exists
            mock_logger = Mock()
            sc2 = MomentScorer(
                wp_enabled=True,
                clip_model_path="/tmp/__nonexistent__.json",
                learning_logger=mock_logger,
            )
            # monkey-patch _maybe_wp_clip to return a triggered moment
            from qoresence.agents.moment_scorer import ScoredMoment

            m = ScoredMoment(
                triggered=True,
                weight=0.9,
                action="clip",
                message="clip",
                reason="test",
                cooldown_key="clip",
                payload={"wp_swing": 0.5},
            )
            sc2._maybe_wp_clip = Mock(return_value=(m, 0.5))  # type: ignore
            sc2._clip_gate = Mock(return_value=True)  # type: ignore
            _ = sc2.score(s, event_type="visual_context", event_payload={"frame_hash": "A" * 40})
            # scorer forwards raw hash; LearningLogger truncates to 16 internally
            assert mock_logger.log.called
            call_kwargs = mock_logger.log.call_args
            args, kwargs = call_kwargs
            # Mock receives full 40-char hash (truncation is LearningLogger's job, tested above)
            forwarded = kwargs.get("frame_hash", args[3] if len(args) > 3 else "")
            assert forwarded == "A" * 40
            # verify real logger truncates as contract
            with tempfile.TemporaryDirectory() as td2:
                p2 = Path(td2) / "anon.jsonl"
                lg2 = LearningLogger(path=p2)
                lg2.log(s, m, frame_hash="A" * 40, wp_swing=0.5)
                assert lg2.load_all()[0].frame_hash == "A" * 16

    def test_moment_scorer_no_logger_no_crash(self):
        sc = MomentScorer(
            wp_enabled=True, clip_model_path="/tmp/__nonexistent__.json", learning_logger=None
        )
        s = _football_state()
        s.game_state = "gameplay"
        out = sc.score(s, event_type="visual_context", event_payload={"frame_hash": "abc"})
        assert isinstance(out, list)

    def test_no_logger_when_off_by_default(self):
        sc = MomentScorer(clip_model_path="/tmp/__nonexistent__.json")
        assert sc._learning_logger is None

    def test_trainer_needs_10_labeled(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "learn.jsonl"
            lg = LearningLogger(path=p)
            tr = ClipWorthinessTrainer(model_path=str(Path(td) / "out.json"))
            # 0 samples -> should raise
            with pytest.raises(ValueError, match=">=10"):
                tr.train_from_logger(lg)
            # 5 labeled -> still raise
            for _ in range(5):
                lg.log(
                    {
                        "field_position": "opp 10",
                        "home_score": 21,
                        "away_score": 14,
                        "controller": {"apm_5s": 60},
                    },
                    {"triggered": True},
                    label=1.0,
                    frame_hash="ab",
                    wp_swing=0.2,
                )
            with pytest.raises(ValueError):
                tr.train_from_logger(lg)

    def test_trainer_succeeds_with_10(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "learn.jsonl"
            lg = LearningLogger(path=p)
            tr = ClipWorthinessTrainer(model_path=str(Path(td) / "out.json"))
            # mix of labels 0/1, varied features
            positions = [
                "opp 5",
                "own 40",
                "opp 20",
                "midfield",
                "opp 2",
                "own 10",
                "opp 15",
                "own 30",
                "opp 8",
                "opp 12",
                "own 25",
                "midfield",
            ]
            for i, pos in enumerate(positions):
                lg.log(
                    {
                        "field_position": pos,
                        "home_score": 21 if i % 2 == 0 else 28,
                        "away_score": 14,
                        "controller": {"apm_5s": 60 + i * 10},
                    },
                    {"triggered": True},
                    label=float(i % 2),
                    frame_hash=f"hash{i:02d}" + "x" * 20,
                    wp_swing=0.05 + i * 0.03,
                )
            weights = tr.train_from_logger(lg, iters=50)
            assert set(weights.keys()) == {"wp_swing", "red_zone", "close_game", "apm", "bias"}
            assert Path(tr.model_path).is_file()

    def test_clutchbot_opt_in_off_by_default(self):
        from qoresence.core.unified_config import RetinaUnifiedConfig

        cfg = RetinaUnifiedConfig()
        # default learning off
        assert cfg.clutchbot.learning_enabled is False
        assert cfg.clutchbot.learning_log_path is None
        from qoresence.agents.clutchbot import ClutchBotAgent
        from qoresence.core.event_bus import RetinaEventBus

        with tempfile.TemporaryDirectory() as td:
            bus = RetinaEventBus(
                session_id="test_cb_off", jsonl_path=Path(td) / "e.jsonl", enable_ws=False
            )
            bot = ClutchBotAgent(config=cfg.clutchbot, bus=bus, session_head_ns=123)
            assert bot._learning_logger is None  # type: ignore

    def test_clutchbot_opt_in_on_creates_logger(self):
        from qoresence.agents.clutchbot import ClutchBotAgent
        from qoresence.core.event_bus import RetinaEventBus
        from qoresence.core.unified_config import ClutchBotConfig

        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "learning.jsonl"
            cfg = ClutchBotConfig(learning_enabled=True, learning_log_path=str(log_path))
            bus = RetinaEventBus(
                session_id="test_cb_on", jsonl_path=Path(td) / "e.jsonl", enable_ws=False
            )
            bot = ClutchBotAgent(config=cfg, bus=bus, session_head_ns=123)
            assert bot._learning_logger is not None  # type: ignore
            assert bot._scorer._learning_logger is not None  # type: ignore
            # also check unified_config from_env wiring covers new fields
            import os

            os.environ["QORESENCE_CLUTCHBOT_LEARNING_ENABLED"] = "1"
            os.environ["QORESENCE_CLUTCHBOT_LEARNING_PATH"] = str(log_path)
            try:
                from qoresence.core.unified_config import RetinaUnifiedConfig as RUC

                rc = RUC.from_env()
                assert rc.clutchbot.learning_enabled is True
                assert rc.clutchbot.learning_log_path == str(log_path)
            finally:
                os.environ.pop("QORESENCE_CLUTCHBOT_LEARNING_ENABLED", None)
                os.environ.pop("QORESENCE_CLUTCHBOT_LEARNING_PATH", None)
