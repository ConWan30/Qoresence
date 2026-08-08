"""Tests for the Qwen3.6-VL adapter scaffold (Trio P5)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from qoresence.vision.qwen_vlm_adapter import (
    QwenVLMAdapter,
    create_local_vlm,
    get_adapter_path,
    get_prompt_for_category,
)


# ── Prompt templates ─────────────────────────────────────────────────────────


def test_football_prompt_template():
    """Football prompt should mention scoreboard fields."""
    prompt = get_prompt_for_category("football")
    assert "home_score" in prompt
    assert "quarter" in prompt
    assert "down" in prompt
    assert "field_position" in prompt


def test_shooter_prompt_template():
    """Shooter prompt should mention HUD fields."""
    prompt = get_prompt_for_category("shooter")
    assert "kills" in prompt
    assert "deaths" in prompt
    assert "health" in prompt


def test_default_prompt_template():
    """Default prompt should be returned for unknown categories."""
    prompt = get_prompt_for_category("unknown")
    assert "game_state" in prompt


def test_none_category_uses_default():
    prompt = get_prompt_for_category(None)
    assert "game_state" in prompt


# ── Adapter path resolution ──────────────────────────────────────────────────


def test_adapter_path_returns_none_if_not_found():
    """get_adapter_path should return None if no adapter exists."""
    assert get_adapter_path("nonexistent_profile") is None


def test_adapter_path_returns_none_for_none_profile():
    assert get_adapter_path(None) is None


def test_adapter_path_finds_existing(tmp_path):
    """get_adapter_path should find an existing adapter directory."""
    import qoresence.vision.qwen_vlm_adapter as mod

    # Create a temporary adapter directory
    adapter_dir = tmp_path / "ncaa_football_27.lora"
    adapter_dir.mkdir()

    # Patch the _ADAPTERS_DIR
    original = mod._ADAPTERS_DIR
    mod._ADAPTERS_DIR = tmp_path
    try:
        result = get_adapter_path("ncaa_football_27")
        assert result is not None
        assert result.exists()
    finally:
        mod._ADAPTERS_DIR = original


# ── QwenVLMAdapter fallback ──────────────────────────────────────────────────


def test_qwen_adapter_falls_back_without_env():
    """QwenVLMAdapter should fall back to LocalVLMClient without env var."""
    # Ensure env var is not set
    old = os.environ.pop("QORESENCE_LOCAL_VLM", None)
    try:
        adapter = QwenVLMAdapter(profile_id="ncaa_football_27", game_category="football")
        assert adapter.available is False
        assert adapter.mode == "fallback"
        assert adapter._fallback is not None
    finally:
        if old is not None:
            os.environ["QORESENCE_LOCAL_VLM"] = old


def test_qwen_adapter_stats():
    """QwenVLMAdapter should return stats."""
    adapter = QwenVLMAdapter()
    stats = adapter.stats()
    assert "calls" in stats
    assert "model" in stats
    assert "adapter_loaded" in stats


def test_qwen_adapter_does_not_crash_on_analyze():
    """QwenVLMAdapter should not crash when analyzing a frame (fallback)."""
    import numpy as np

    adapter = QwenVLMAdapter(game_category="football")
    # Should use fallback (LocalVLMClient) without crashing
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    vc = adapter.analyze_frame(frame, frame_seq=1)
    assert vc is not None
    assert vc.game_state  # should have some game state


# ── Factory function ─────────────────────────────────────────────────────────


def test_create_local_vlm_returns_local_by_default():
    """create_local_vlm should return LocalVLMClient by default."""
    old = os.environ.pop("QORESENCE_LOCAL_VLM", None)
    try:
        client = create_local_vlm()
        # Should be LocalVLMClient (not QwenVLMAdapter)
        assert not isinstance(client, QwenVLMAdapter)
    finally:
        if old is not None:
            os.environ["QORESENCE_LOCAL_VLM"] = old


def test_create_local_vlm_returns_qwen_when_preferred():
    """create_local_vlm should try Qwen when prefer_qwen=True."""
    client = create_local_vlm(prefer_qwen=True, profile_id="test", game_category="football")
    # Even if Qwen isn't available, it should return a QwenVLMAdapter
    # (which will fall back to LocalVLMClient internally)
    assert isinstance(client, QwenVLMAdapter)
    assert client.available is False  # no model installed


# ── Response parsing ─────────────────────────────────────────────────────────


def test_parse_qwen_response_football():
    """_parse_qwen_response should parse football fields from JSON."""
    adapter = QwenVLMAdapter(game_category="football")
    response = '''```json
    {
        "game_state": "gameplay",
        "home_score": 14,
        "away_score": 7,
        "quarter": 2,
        "down": 3,
        "yards_to_go": 5,
        "possession": "home",
        "field_position": "OPP 25",
        "game_clock": "8:32"
    }
    ```'''
    vc = adapter._parse_qwen_response(response, frame_seq=42)
    assert vc.game_state == "gameplay"
    assert vc.home_score == 14
    assert vc.away_score == 7
    assert vc.quarter == 2
    assert vc.down == 3
    assert vc.yards_to_go == 5
    assert vc.possession == "home"
    assert vc.field_position == "OPP 25"
    assert vc.clock_seconds == 512  # 8*60 + 32
    assert vc.model == "qwen-vlm"


def test_parse_qwen_response_shooter():
    """_parse_qwen_response should parse shooter fields from JSON."""
    adapter = QwenVLMAdapter(game_category="shooter")
    response = '{"game_state": "gameplay", "kills": 15, "deaths": 3, "score": 2500, "health": 80}'
    vc = adapter._parse_qwen_response(response, frame_seq=1)
    assert vc.game_state == "gameplay"
    assert vc.kills == 15
    assert vc.deaths == 3
    assert vc.score == 2500


def test_parse_qwen_response_invalid_json():
    """_parse_qwen_response should handle invalid JSON gracefully."""
    adapter = QwenVLMAdapter(game_category="football")
    vc = adapter._parse_qwen_response("not json at all", frame_seq=1)
    assert vc.game_state == "gameplay"
    assert vc.confidence < 0.5  # low confidence for failed parse


def test_parse_qwen_response_partial_fields():
    """_parse_qwen_response should handle partial fields."""
    adapter = QwenVLMAdapter(game_category="football")
    response = '{"game_state": "menu", "home_score": 0}'
    vc = adapter._parse_qwen_response(response, frame_seq=1)
    assert vc.game_state == "menu"
    assert vc.home_score == 0
    # Other fields should be None
    assert vc.away_score is None
    assert vc.quarter is None
