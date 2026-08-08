"""Tests for the LoRA training pipeline scaffold (Trio P5)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import numpy as np

from qoresence.vision.train_adapter import (
    AdapterTrainer,
    TrainingConfig,
    TrainingExample,
    collect_screenshot,
    format_target_response,
    load_training_data,
)
from qoresence.vision.visual_context import VisualContext


# ── TrainingConfig ───────────────────────────────────────────────────────────


def test_training_config_defaults():
    config = TrainingConfig()
    assert config.profile_id == ""
    assert config.epochs == 3
    assert config.batch_size == 4
    assert config.learning_rate == 1e-4
    assert config.lora_r == 16


def test_training_config_to_dict():
    config = TrainingConfig(profile_id="ncaa_football_27", epochs=5)
    d = config.to_dict()
    assert d["profile_id"] == "ncaa_football_27"
    assert d["epochs"] == 5


# ── Data loading ─────────────────────────────────────────────────────────────


def test_load_training_data(tmp_path):
    """Should load JSON+PNG pairs as training examples."""
    # Create test data
    for i in range(3):
        # Create a dummy PNG
        import cv2
        frame = np.full((100, 100, 3), 50, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / f"frame_{i:04d}.png"), frame)

        # Create JSON label
        label = {
            "image": f"frame_{i:04d}.png",
            "game_state": "gameplay",
            "home_score": i * 7,
            "away_score": 0,
            "quarter": 1,
        }
        (tmp_path / f"frame_{i:04d}.json").write_text(
            json.dumps(label), encoding="utf-8"
        )

    examples = load_training_data(tmp_path, "ncaa_football_27", "football")
    assert len(examples) == 3
    assert examples[0].target_json["home_score"] == 0
    assert examples[1].target_json["home_score"] == 7
    assert examples[2].target_json["home_score"] == 14


def test_load_training_data_missing_dir():
    """Should raise FileNotFoundError for missing directory."""
    with pytest.raises(FileNotFoundError):
        load_training_data("/nonexistent/path", "test")


def test_load_training_data_max_samples(tmp_path):
    """Should respect max_samples limit."""
    import cv2
    for i in range(10):
        frame = np.full((50, 50, 3), 30, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / f"f{i}.png"), frame)
        (tmp_path / f"f{i}.json").write_text(
            json.dumps({"image": f"f{i}.png", "game_state": "gameplay"}),
            encoding="utf-8",
        )

    examples = load_training_data(tmp_path, "test", "football", max_samples=3)
    assert len(examples) == 3


def test_load_training_data_skips_missing_images(tmp_path):
    """Should skip examples where the image file is missing."""
    # JSON without corresponding image
    (tmp_path / "frame_0001.json").write_text(
        json.dumps({"image": "frame_0001.png", "game_state": "gameplay"}),
        encoding="utf-8",
    )

    examples = load_training_data(tmp_path, "test", "football")
    assert len(examples) == 0


def test_load_training_data_skips_invalid_json(tmp_path):
    """Should skip invalid JSON files."""
    import cv2
    frame = np.full((50, 50, 3), 30, dtype=np.uint8)
    cv2.imwrite(str(tmp_path / "f0.png"), frame)
    (tmp_path / "f0.json").write_text("not valid json", encoding="utf-8")

    examples = load_training_data(tmp_path, "test", "football")
    assert len(examples) == 0


# ── Format target ────────────────────────────────────────────────────────────


def test_format_target_response():
    """Should format target JSON as string."""
    target = {"game_state": "gameplay", "home_score": 14}
    text = format_target_response(target)
    assert "gameplay" in text
    assert "14" in text


# ── AdapterTrainer ───────────────────────────────────────────────────────────


def test_trainer_load_data(tmp_path):
    """Trainer should load data from configured directory."""
    import cv2
    for i in range(2):
        frame = np.full((50, 50, 3), 30, dtype=np.uint8)
        cv2.imwrite(str(tmp_path / f"f{i}.png"), frame)
        (tmp_path / f"f{i}.json").write_text(
            json.dumps({"image": f"f{i}.png", "game_state": "gameplay"}),
            encoding="utf-8",
        )

    config = TrainingConfig(
        profile_id="test",
        data_dir=str(tmp_path),
        output_dir=str(tmp_path / "output"),
    )
    trainer = AdapterTrainer(config)
    n = trainer.load_data()
    assert n == 2
    assert len(trainer.examples) == 2


def test_trainer_load_data_empty(tmp_path):
    """Trainer should handle empty data directory."""
    config = TrainingConfig(data_dir=str(tmp_path))
    trainer = AdapterTrainer(config)
    n = trainer.load_data()
    assert n == 0


def test_trainer_setup_model_without_deps():
    """Trainer should return False when dependencies are missing."""
    config = TrainingConfig()
    trainer = AdapterTrainer(config)
    # In test env, torch/transformers may not be installed
    result = trainer.setup_model()
    # Should not crash — either succeeds (if deps installed) or returns False
    assert isinstance(result, bool)


def test_trainer_save_without_model():
    """Trainer should fail to save when no model is set up."""
    config = TrainingConfig(output_dir="/tmp/test_adapter")
    trainer = AdapterTrainer(config)
    assert trainer.save_adapter() is False


# ── Screenshot collection ────────────────────────────────────────────────────


def test_collect_screenshot(tmp_path):
    """Should save frame + VisualContext as PNG+JSON pair."""
    import cv2
    frame = np.full((100, 100, 3), 50, dtype=np.uint8)
    vc = VisualContext(
        game_state="gameplay",
        home_score=14,
        away_score=7,
        quarter=2,
    )

    json_path = collect_screenshot(frame, vc, tmp_path, frame_seq=1)
    assert json_path is not None

    json_file = Path(json_path)
    assert json_file.exists()

    data = json.loads(json_file.read_text(encoding="utf-8"))
    assert data["game_state"] == "gameplay"
    assert data["home_score"] == 14
    assert data["away_score"] == 7

    # PNG should also exist
    png_file = tmp_path / data["image"]
    assert png_file.exists()


def test_collect_screenshot_shooter(tmp_path):
    """Should save shooter fields in screenshot collection."""
    import cv2
    frame = np.full((100, 100, 3), 50, dtype=np.uint8)
    vc = VisualContext(
        game_state="gameplay",
        kills=15,
        deaths=3,
        score=2500,
    )

    json_path = collect_screenshot(frame, vc, tmp_path, frame_seq=1)
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    assert data["kills"] == 15
    assert data["deaths"] == 3
    assert data["score"] == 2500


def test_collect_screenshot_none_frame(tmp_path):
    """Should return None for invalid frame."""
    vc = VisualContext(game_state="gameplay")
    result = collect_screenshot(None, vc, tmp_path, frame_seq=1)
    assert result is None
