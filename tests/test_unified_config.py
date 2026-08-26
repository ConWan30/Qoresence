"""
Unit tests for Qoresence Unified Configuration (Phase 1).

Tests the safety defaults, validation rules, and first-class game profiles.
"""

from __future__ import annotations

import pytest

from qoresence.core.unified_config import (
    CALL_OF_DUTY_PROFILE,
    GAME_PROFILE_REGISTRY,
    NCAA_FOOTBALL_27_PROFILE,
    ControllerConfig,
    FusionWeights,
    GameProfile,
    GameProfileId,
    OutcomeConfig,
    RetinaUnifiedConfig,
    ScreenConfig,
    StreamerConfig,
    VisualConfig,
    get_game_profile,
    register_game_profile,
)


class TestFusionWeights:
    """Tests for FusionWeights validation."""

    def test_default_weights_sum_to_one(self):
        weights = FusionWeights()
        weights.validate()  # Should not raise

    def test_custom_weights_valid(self):
        weights = FusionWeights(
            streamer_presence_sync=0.3,
            controller_causal_density=0.3,
            screen_coupling_score=0.2,
            outcome_coherence=0.1,
            visual_confirmation=0.1,
        )
        weights.validate()

    def test_weights_must_sum_to_one(self):
        weights = FusionWeights(
            streamer_presence_sync=0.5,
            controller_causal_density=0.5,
            screen_coupling_score=0.0,
            outcome_coherence=0.0,
            visual_confirmation=0.0,
        )
        # Sum = 1.0, should be valid
        weights.validate()

    def test_weights_reject_invalid_sum(self):
        weights = FusionWeights(
            streamer_presence_sync=0.5,
            controller_causal_density=0.5,
            screen_coupling_score=0.2,
            outcome_coherence=0.1,
            visual_confirmation=0.1,
        )
        # Sum = 1.4, should raise
        with pytest.raises(ValueError, match="sum to 1.0"):
            weights.validate()


class TestGameProfiles:
    """Tests for first-class game profiles."""

    def test_ncaa_football_27_profile_exists(self):
        assert GameProfileId.NCAA_FOOTBALL_27 in GAME_PROFILE_REGISTRY
        profile = GAME_PROFILE_REGISTRY[GameProfileId.NCAA_FOOTBALL_27]
        assert profile.display_name == "NCAA College Football 27"
        assert profile.category == "football"

    def test_call_of_duty_profile_exists(self):
        assert GameProfileId.CALL_OF_DUTY in GAME_PROFILE_REGISTRY
        profile = GAME_PROFILE_REGISTRY[GameProfileId.CALL_OF_DUTY]
        assert profile.display_name == "Call of Duty (Warzone / Multiplayer)"
        assert profile.category == "shooter"

    def test_ncaa_event_types_defined(self):
        profile = NCAA_FOOTBALL_27_PROFILE
        expected = {
            "snap",
            "down_advanced",
            "first_down",
            "score_changed",
            "touchdown",
            "field_goal",
            "safety",
            "two_point_conversion",
            "playclock_reset",
            "quarter_changed",
            "two_minute_warning",
            "possession_changed",
            "timeout_called",
            "penalty",
            "turnover",
            "red_zone_entry",
        }
        assert set(profile.event_types) == expected

    def test_ncaa_outcome_fields_defined(self):
        profile = NCAA_FOOTBALL_27_PROFILE
        expected = {
            "home_score",
            "away_score",
            "quarter",
            "down",
            "yards_to_go",
            "possession",
            "play_clock",
            "game_clock",
            "field_position",
        }
        assert set(profile.outcome_fields) == expected

    def test_cod_event_types_defined(self):
        profile = CALL_OF_DUTY_PROFILE
        expected = {
            "kill",
            "death",
            "assist",
            "streak",
            "objective_capture",
            "objective_defend",
            "round_start",
            "round_end",
            "match_start",
            "match_end",
        }
        assert set(profile.event_types) == expected

    def test_cod_outcome_fields_defined(self):
        profile = CALL_OF_DUTY_PROFILE
        expected = {
            "kills",
            "deaths",
            "assists",
            "score",
            "streak_count",
            "team",
            "mode",
            "map",
        }
        assert set(profile.outcome_fields) == expected

    def test_get_game_profile(self):
        profile = get_game_profile(GameProfileId.NCAA_FOOTBALL_27)
        assert profile.profile_id == GameProfileId.NCAA_FOOTBALL_27

    def test_register_game_profile(self):
        # GameProfileId is an enum with fixed values; register_game_profile
        # works with any GameProfile that has a valid profile_id from the enum
        original = GAME_PROFILE_REGISTRY.get(GameProfileId.NCAA_FOOTBALL_27)
        custom = GameProfile(
            profile_id=GameProfileId.NCAA_FOOTBALL_27,  # reuse existing for test
            display_name="Custom Game",
            event_types=("event1", "event2"),
            outcome_fields=("field1",),
            category="other",
        )
        try:
            # Should be able to register (overwrites existing)
            register_game_profile(custom)
            assert GameProfileId.NCAA_FOOTBALL_27 in GAME_PROFILE_REGISTRY
            assert get_game_profile(GameProfileId.NCAA_FOOTBALL_27) == custom
        finally:
            if original:
                GAME_PROFILE_REGISTRY[GameProfileId.NCAA_FOOTBALL_27] = original


class TestRetinaUnifiedConfigDefaults:
    """Tests proving ALL lobes default to OFF."""

    def test_all_lobes_default_false(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
        )
        assert config.streamer.enabled is False
        assert config.controller.enabled is False
        assert config.screen.enabled is False
        assert config.outcome.enabled is False
        assert config.visual.enabled is False
        assert config.haptic_probe.enabled is False
        assert config.otel.enabled is False

    def test_safety_contracts_default_true(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
        )
        assert config.eye_check_required is True
        assert config.never_claim_humanity is True

    def test_fusion_weights_default_valid(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
        )
        assert config.fusion_weights.streamer_presence_sync == 0.25
        assert config.fusion_weights.controller_causal_density == 0.25
        assert config.fusion_weights.screen_coupling_score == 0.20
        assert config.fusion_weights.outcome_coherence == 0.15
        assert config.fusion_weights.visual_confirmation == 0.15


class TestRetinaUnifiedConfigValidation:
    """Tests for configuration validation rules."""

    def test_valid_config_passes(self):
        config = RetinaUnifiedConfig(
            session_id="valid_session",
            session_head_ns=1234567890123456789,
            device_id_hex="a" * 64,
        )
        errors = config.validate()
        assert errors == []

    def test_rejects_missing_session_id(self):
        config = RetinaUnifiedConfig(
            session_id="",
            session_head_ns=1234567890,
        )
        errors = config.validate()
        assert any("session_id is required" in e for e in errors)

    def test_rejects_zero_session_head_ns(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=0,
        )
        errors = config.validate()
        assert any("session_head_ns must be a positive integer" in e for e in errors)

    def test_rejects_negative_session_head_ns(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=-1,
        )
        errors = config.validate()
        assert any("session_head_ns must be a positive integer" in e for e in errors)

    def test_rejects_invalid_device_id_hex_length(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            device_id_hex="abc",  # too short
        )
        errors = config.validate()
        assert any("64 hex characters" in e for e in errors)

    def test_rejects_invalid_device_id_hex_format(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            device_id_hex="g" * 64,  # not hex
        )
        errors = config.validate()
        assert any("valid hexadecimal" in e for e in errors)

    def test_rejects_eye_check_false(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            eye_check_required=False,
        )
        errors = config.validate()
        assert any("eye_check_required must be True" in e for e in errors)

    def test_rejects_claim_humanity_false(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            never_claim_humanity=False,
        )
        errors = config.validate()
        assert any("never_claim_humanity must be True" in e for e in errors)

    def test_rejects_invalid_fusion_weights(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            fusion_weights=FusionWeights(
                streamer_presence_sync=0.5,
                controller_causal_density=0.5,
                screen_coupling_score=0.2,
                outcome_coherence=0.1,
                visual_confirmation=0.1,
            ),
        )
        errors = config.validate()
        assert any("sum to 1.0" in e for e in errors)

    def test_streamer_eye_check_required_when_enabled(self):
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            streamer=StreamerConfig(enabled=True, eye_check_required=False),
        )
        errors = config.validate()
        assert any("streamer.eye_check_required must be True" in e for e in errors)

    def test_outcome_unknown_game_profile_rejected(self):
        # Test that validation rejects a profile not in the registry
        # We create a valid enum value but remove it from registry temporarily
        config = RetinaUnifiedConfig(
            session_id="test_session",
            session_head_ns=1234567890,
            outcome=OutcomeConfig(enabled=True, game_profile=GameProfileId.NCAA_FOOTBALL_27),
        )
        # Remove from registry to simulate unknown
        original = GAME_PROFILE_REGISTRY.pop(GameProfileId.NCAA_FOOTBALL_27, None)
        try:
            errors = config.validate()
            assert any("Unknown game profile" in e for e in errors)
        finally:
            if original:
                GAME_PROFILE_REGISTRY[GameProfileId.NCAA_FOOTBALL_27] = original


class TestRetinaUnifiedConfigFactoryMethods:
    """Tests for factory methods."""

    def test_create_session_generates_ids(self):
        config = RetinaUnifiedConfig.create_session()
        assert config.session_id.startswith("qoresence_")
        assert config.session_head_ns > 0
        assert config.device_id_hex == ""

    def test_create_session_with_custom_ids(self):
        config = RetinaUnifiedConfig.create_session(
            session_id="my_custom_session",
            device_id_hex="b" * 64,
        )
        assert config.session_id == "my_custom_session"
        assert config.device_id_hex == "b" * 64

    def test_is_valid_returns_bool(self):
        valid = RetinaUnifiedConfig(
            session_id="test",
            session_head_ns=1234567890,
        )
        invalid = RetinaUnifiedConfig(
            session_id="",
            session_head_ns=1234567890,
        )
        assert valid.is_valid() is True
        assert invalid.is_valid() is False


class TestLobeConfigs:
    """Tests for individual lobe configuration dataclasses."""

    def test_streamer_config_defaults(self):
        cfg = StreamerConfig()
        assert cfg.enabled is False
        assert cfg.device_index == 0
        assert cfg.source_kind == "uvc_card"
        assert cfg.fps_target == 15.0
        assert cfg.eye_check_required is True

    def test_controller_config_defaults(self):
        cfg = ControllerConfig()
        assert cfg.enabled is False
        assert cfg.poll_rate_hz == 1000.0
        assert cfg.buffer_size == 1000

    def test_screen_config_defaults(self):
        cfg = ScreenConfig()
        assert cfg.enabled is False
        assert cfg.capture_method == "wgc"
        assert cfg.fps_target == 60.0

    def test_outcome_config_defaults(self):
        cfg = OutcomeConfig()
        assert cfg.enabled is False
        assert cfg.game_profile == GameProfileId.NCAA_FOOTBALL_27
        assert cfg.confidence_threshold == 0.7

    def test_visual_config_defaults(self):
        cfg = VisualConfig()
        assert cfg.enabled is False
        assert cfg.frame_sample_rate == 30
        assert cfg.game_category == "football"


class TestConfigAccessors:
    """Tests for game profile accessor methods."""

    def test_active_game_profile_returns_correct(self):
        config = RetinaUnifiedConfig(
            session_id="test",
            session_head_ns=1234567890,
            outcome=OutcomeConfig(game_profile=GameProfileId.CALL_OF_DUTY),
        )
        profile = config.active_game_profile
        assert profile.profile_id == GameProfileId.CALL_OF_DUTY
        assert profile.category == "shooter"

    def test_get_event_types_for_profile(self):
        config = RetinaUnifiedConfig(
            session_id="test",
            session_head_ns=1234567890,
        )
        events = config.get_event_types_for_profile()
        assert "snap" in events
        assert "kill" not in events  # NCAA profile doesn't have kill

    def test_get_outcome_fields_for_profile(self):
        config = RetinaUnifiedConfig(
            session_id="test",
            session_head_ns=1234567890,
        )
        fields = config.get_outcome_fields_for_profile()
        assert "home_score" in fields
        assert "kills" not in fields  # NCAA profile doesn't have kills


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
