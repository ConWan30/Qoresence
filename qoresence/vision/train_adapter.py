"""LoRA training pipeline for Qwen3.6-VL game-profile adapters (Trio P5).

This module provides the training pipeline for fine-tuning a LoRA adapter
per game profile on labeled screenshot data. The adapter is then loaded
by QwenVLMAdapter at inference time.

Pipeline:
    1. Collect labeled screenshots (JSON + PNG pairs)
    2. Format as VQA training examples
    3. Train LoRA adapter on frozen Qwen3.6-VL base
    4. Save adapter to models/adapters/<profile_id>.lora/
    5. (Optional) Export to ONNX for <100ms inference

Data format (per screenshot):
    screenshots/<profile_id>/frame_0001.json:
    {
        "image": "frame_0001.png",
        "game_state": "gameplay",
        "home_score": 14,
        "away_score": 7,
        "quarter": 2,
        "down": 3,
        ...
    }

Requirements (not installed by default):
    - torch
    - transformers
    - peft
    - PIL
    - GPU with >=8GB VRAM recommended

Usage:
    python -m qoresence.vision.train_adapter \
        --profile ncaa_football_27 \
        --data screenshots/ncaa_football_27/ \
        --output models/adapters/ncaa_football_27.lora/ \
        --epochs 3 \
        --batch-size 4 \
        --learning-rate 1e-4
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qoresence.vision.qwen_vlm_adapter import get_prompt_for_category
from qoresence.vision.visual_context import VisualContext

log = logging.getLogger(__name__)


@dataclass
class TrainingConfig:
    """Configuration for LoRA adapter training."""

    profile_id: str = ""
    data_dir: str = ""
    output_dir: str = ""
    base_model: str = "Qwen/Qwen3.6-VL-7B-Instruct"
    game_category: str = "football"

    # LoRA hyperparameters
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "v_proj", "k_proj", "o_proj",
    ])

    # Training hyperparameters
    epochs: int = 3
    batch_size: int = 4
    learning_rate: float = 1e-4
    warmup_steps: int = 50
    max_steps: int = 0  # 0 = use epochs
    save_steps: int = 100
    eval_steps: int = 100

    # Data
    max_samples: int = 0  # 0 = all
    image_size: int = 640
    max_text_length: int = 256

    # Device
    device: str = "auto"
    fp16: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "base_model": self.base_model,
            "game_category": self.game_category,
            "lora_r": self.lora_r,
            "lora_alpha": self.lora_alpha,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
        }


@dataclass
class TrainingExample:
    """A single training example for VQA fine-tuning."""

    image_path: str
    prompt: str
    target_json: dict[str, Any]
    target_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_path": self.image_path,
            "prompt": self.prompt,
            "target": self.target_json,
        }


def load_training_data(
    data_dir: str | Path,
    profile_id: str,
    game_category: str = "football",
    max_samples: int = 0,
) -> list[TrainingExample]:
    """Load labeled screenshots from a directory.

    Expects JSON files with a corresponding image file (same name, .png).
    """
    data_dir = Path(data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"Training data directory not found: {data_dir}")

    prompt = get_prompt_for_category(game_category)
    examples: list[TrainingExample] = []

    json_files = sorted(data_dir.glob("*.json"))
    if max_samples > 0:
        json_files = json_files[:max_samples]

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Failed to load %s: %s", jf, e)
            continue

        # Find the corresponding image
        image_name = data.get("image", jf.stem + ".png")
        image_path = data_dir / image_name
        if not image_path.exists():
            log.debug("Image not found for %s: %s", jf.name, image_path)
            continue

        # Build target text (JSON response the model should produce)
        target_json = {k: v for k, v in data.items() if k != "image"}
        target_text = json.dumps(target_json, indent=2)

        examples.append(TrainingExample(
            image_path=str(image_path),
            prompt=prompt,
            target_json=target_json,
            target_text=target_text,
        ))

    log.info("Loaded %d training examples from %s", len(examples), data_dir)
    return examples


def format_target_response(target_json: dict[str, Any]) -> str:
    """Format a target JSON dict as the expected model response."""
    return json.dumps(target_json)


def create_lora_config(config: TrainingConfig):
    """Create a LoRA configuration for PEFT.

    Returns a LoraConfig object if peft is installed, else None.
    """
    try:
        from peft import LoraConfig, TaskType

        return LoraConfig(
            r=config.lora_r,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            target_modules=config.target_modules,
            task_type=TaskType.CAUSAL_LM,
        )
    except ImportError:
        log.warning("peft not installed — cannot create LoRA config")
        return None


class AdapterTrainer:
    """Training pipeline for LoRA adapters on Qwen3.6-VL.

    This is a scaffold that implements the full training loop when
    torch + transformers + peft are available. When they're not
    installed, it provides data loading and config management but
    cannot actually train.
    """

    def __init__(self, config: TrainingConfig) -> None:
        self.config = config
        self.examples: list[TrainingExample] = []
        self._model = None
        self._processor = None
        self._available = False

    def load_data(self) -> int:
        """Load training data from the configured directory."""
        self.examples = load_training_data(
            data_dir=self.config.data_dir,
            profile_id=self.config.profile_id,
            game_category=self.config.game_category,
            max_samples=self.config.max_samples,
        )
        return len(self.examples)

    def setup_model(self) -> bool:
        """Load the base model and prepare for LoRA training.

        Returns True if successful, False if dependencies are missing.
        """
        try:
            import torch
            from transformers import AutoModelForVision2Seq, AutoProcessor

            device = self.config.device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"

            log.info("Loading base model: %s on %s", self.config.base_model, device)
            self._processor = AutoProcessor.from_pretrained(self.config.base_model)
            self._model = AutoModelForVision2Seq.from_pretrained(
                self.config.base_model,
                torch_dtype=torch.float16 if self.config.fp16 and device == "cuda" else torch.float32,
                device_map=device,
            )

            # Apply LoRA
            lora_config = create_lora_config(self.config)
            if lora_config:
                from peft import get_peft_model
                self._model = get_peft_model(self._model, lora_config)
                self._model.print_trainable_parameters()

            self._available = True
            return True
        except ImportError as e:
            log.warning("Training dependencies not installed: %s", e)
            return False
        except Exception as e:
            log.warning("Model setup failed: %s", e)
            return False

    def train(self) -> bool:
        """Run the training loop.

        Returns True if training completed successfully.
        """
        if not self._available:
            log.error("Model not set up — call setup_model() first")
            return False
        if not self.examples:
            log.error("No training data — call load_data() first")
            return False

        try:
            import torch
            from torch.utils.data import DataLoader

            log.info(
                "Starting training: %d examples, %d epochs, lr=%e",
                len(self.examples), self.config.epochs, self.config.learning_rate,
            )

            # Create optimizer
            optimizer = torch.optim.AdamW(
                self._model.parameters(),
                lr=self.config.learning_rate,
            )

            # Simple training loop (scaffold — real implementation would use
            # Trainer with proper dataset collation, eval, checkpointing)
            for epoch in range(self.config.epochs):
                total_loss = 0.0
                # Shuffle examples
                import random
                random.shuffle(self.examples)

                for i in range(0, len(self.examples), self.config.batch_size):
                    batch = self.examples[i:i + self.config.batch_size]
                    loss = self._train_batch(batch, optimizer)
                    total_loss += loss

                    if (i // self.config.batch_size) % self.config.save_steps == 0:
                        log.info(
                            "Epoch %d step %d: loss=%.4f",
                            epoch + 1, i // self.config.batch_size, loss,
                        )

                avg_loss = total_loss / max(1, len(self.examples) // self.config.batch_size)
                log.info("Epoch %d complete: avg_loss=%.4f", epoch + 1, avg_loss)

            return True
        except Exception as e:
            log.exception("Training failed: %s", e)
            return False

    def _train_batch(self, batch: list[TrainingExample], optimizer) -> float:
        """Train a single batch. Returns the average loss."""
        import torch
        from PIL import Image

        images = []
        texts = []
        for ex in batch:
            img = Image.open(ex.image_path).convert("RGB")
            # Resize to configured size
            img = img.resize((self.config.image_size, self.config.image_size))
            images.append(img)
            texts.append(ex.prompt + "\n" + format_target_response(ex.target_json))

        # Process inputs
        inputs = self._processor(
            text=texts, images=images, return_tensors="pt",
            padding=True, truncation=True, max_length=self.config.max_text_length,
        ).to(self._model.device)

        # Forward pass
        outputs = self._model(**inputs, labels=inputs["input_ids"])
        loss = outputs.loss

        # Backward pass
        loss.backward()
        optimizer.step()
        optimizer.zero_grad()

        return loss.item()

    def save_adapter(self, output_dir: str | Path | None = None) -> bool:
        """Save the trained LoRA adapter."""
        output_dir = Path(output_dir or self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not self._available or self._model is None:
            log.error("No trained model to save")
            return False

        try:
            # Save LoRA adapter weights
            if hasattr(self._model, "save_pretrained"):
                self._model.save_pretrained(str(output_dir))
            if self._processor is not None:
                self._processor.save_pretrained(str(output_dir))

            # Save training config
            config_path = output_dir / "training_config.json"
            config_path.write_text(
                json.dumps(self.config.to_dict(), indent=2),
                encoding="utf-8",
            )
            log.info("Adapter saved to %s", output_dir)
            return True
        except Exception as e:
            log.exception("Failed to save adapter: %s", e)
            return False


def collect_screenshot(
    frame,
    visual_context: VisualContext,
    output_dir: str | Path,
    frame_seq: int,
) -> str | None:
    """Save a labeled screenshot for future adapter training.

    Called during live sessions to build a training dataset.
    The frame and its VisualContext are saved as PNG + JSON pair.
    """
    try:
        import cv2
        import numpy as np

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = f"frame_{frame_seq:06d}"
        png_path = output_dir / f"{stem}.png"
        json_path = output_dir / f"{stem}.json"

        # Save frame as PNG
        if hasattr(frame, "shape"):
            cv2.imwrite(str(png_path), frame)
        else:
            return None

        # Save VisualContext as JSON
        vc_dict = {
            "image": png_path.name,
            "game_state": str(visual_context.game_state),
            "game_category": str(visual_context.game_category),
            "confidence": visual_context.confidence,
        }
        # Football fields
        for f in ("home_score", "away_score", "quarter", "down",
                   "yards_to_go", "possession", "field_position", "clock_seconds"):
            val = getattr(visual_context, f, None)
            if val is not None:
                vc_dict[f] = val
        # Shooter fields
        for f in ("kills", "deaths", "score", "health", "ammo"):
            val = getattr(visual_context, f, None)
            if val is not None:
                vc_dict[f] = val

        json_path.write_text(json.dumps(vc_dict, indent=2), encoding="utf-8")
        return str(json_path)
    except Exception as e:
        log.debug("Screenshot collection failed: %s", e)
        return None


def main():
    """CLI entry point for adapter training."""
    import argparse

    parser = argparse.ArgumentParser(description="Train LoRA adapter for Qwen3.6-VL")
    parser.add_argument("--profile", required=True, help="Game profile ID")
    parser.add_argument("--data", required=True, help="Training data directory")
    parser.add_argument("--output", required=True, help="Output adapter directory")
    parser.add_argument("--category", default="football", help="Game category")
    parser.add_argument("--epochs", type=int, default=3, help="Number of epochs")
    parser.add_argument("--batch-size", type=int, default=4, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--lora-r", type=int, default=16, help="LoRA rank")
    parser.add_argument("--max-samples", type=int, default=0, help="Max samples (0=all)")
    args = parser.parse_args()

    config = TrainingConfig(
        profile_id=args.profile,
        data_dir=args.data,
        output_dir=args.output,
        game_category=args.category,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        lora_r=args.lora_r,
        max_samples=args.max_samples,
    )

    trainer = AdapterTrainer(config)

    # Load data
    n = trainer.load_data()
    if n == 0:
        print(f"No training data found in {args.data}")
        return 1

    print(f"Loaded {n} training examples")

    # Setup model
    if not trainer.setup_model():
        print("Failed to set up model. Install torch, transformers, peft.")
        return 1

    # Train
    if not trainer.train():
        print("Training failed")
        return 1

    # Save
    if not trainer.save_adapter():
        print("Failed to save adapter")
        return 1

    print(f"Adapter saved to {args.output}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
