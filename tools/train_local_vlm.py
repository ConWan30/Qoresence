"""Distill a tiny local VLM for Qoresence.

Trains a MobileNet-V2 classifier on synthetic frames + random crops from the
eye-check proof images, using the same green/edge/luma heuristic as pseudo-labels.
Exports to models/qoresence-vlm-distilled.onnx for LocalVLMClient.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch
import torch.nn as nn
import torchvision.transforms as T
from torchvision.models import MobileNet_V2_Weights, mobilenet_v2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qoresence.vision.local_vlm import LocalVLMClient  # noqa: E402

log = logging.getLogger(__name__)

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 3, 1, 1)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 3, 1, 1)


def _heuristic_label(green_ratio: float, edge_density: float, mean_luma: float) -> int:
    """Return 0=football, 1=unknown, 2=menu based on the heuristic rules."""
    has_scoreboard = mean_luma > 30 and edge_density > 0.02
    if green_ratio > 0.06 and has_scoreboard:
        return 0
    if edge_density > 0.06 and green_ratio < 0.08:
        return 2 if mean_luma < 35 else 1
    if mean_luma < 20:
        return 2
    return 1


def _synthetic_frame(label: int, size: int = 224) -> tuple[np.ndarray, int]:
    """Generate a synthetic 224x224 BGR frame and a pseudo-label (0-2)."""
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    if label == 0:  # football
        # Green field with white scoreboard/yard lines and some non-green clutter.
        hue = random.randint(40, 75)
        sat = random.randint(90, 255)
        val = random.randint(80, 220)
        hsv = np.full((size, size, 3), [hue, sat, val], dtype=np.uint8)
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        frame[:] = bgr

        # Scoreboard bar (white) across the top.
        bar_h = random.randint(8, 22)
        frame[:bar_h, :] = (255, 255, 255)

        # Yard lines.
        for _ in range(random.randint(2, 5)):
            y = random.randint(bar_h + 5, size - 5)
            cv2.line(frame, (0, y), (size, y), (255, 255, 255), 1)
        for _ in range(random.randint(0, 2)):
            x = random.randint(5, size - 5)
            cv2.line(frame, (x, 0), (x, size), (255, 255, 255), 1)

        # Simulate players / crowd blobs (non-green, raise edge + luma).
        for _ in range(random.randint(3, 10)):
            x, y = random.randint(0, size - 30), random.randint(bar_h, size - 30)
            color = (random.randint(0, 120), random.randint(0, 120), random.randint(0, 120))
            cv2.circle(frame, (x + 15, y + 15), random.randint(4, 12), color, -1)

    elif label == 2:  # menu / dark
        base = random.randint(2, 18)
        frame[:, :] = (base, base, base)
        # A few dim text/menu bars.
        if random.random() > 0.4:
            bar_h = random.randint(10, 30)
            bar_y = random.randint(20, size - bar_h - 20)
            val = min(255, base + random.randint(15, 40))
            frame[bar_y:bar_y + bar_h, :] = (val, val, val)
        for _ in range(random.randint(0, 4)):
            x, y = random.randint(10, size - 50), random.randint(10, size - 10)
            w, h = random.randint(30, 100), random.randint(4, 12)
            val = min(255, base + random.randint(10, 35))
            cv2.rectangle(frame, (x, y), (x + w, y + h), (val, val, val), -1)

    else:  # unknown / high edge, low green, decent luma
        bg = random.randint(35, 95)
        frame[:, :] = (bg, bg, bg)
        block = random.randint(8, 28)
        for y in range(0, size, block):
            for x in range(0, size, block):
                if ((x // block) + (y // block)) % 2 == 0:
                    val = min(255, bg + random.randint(30, 90))
                    frame[y:y + block, x:x + block] = (val, val, val)
        for _ in range(random.randint(3, 10)):
            x1, y1, x2, y2 = [random.randint(0, size) for _ in range(4)]
            cv2.line(frame, (x1, y1), (x2, y2), (180, 180, 180), 1)

    # Verify pseudo-label with the heuristic.
    small = cv2.resize(frame, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
    green_ratio = float((green > 0).mean())
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float((edges > 0).mean())
    mean_luma = float(gray.mean())
    return frame, _heuristic_label(green_ratio, edge_density, mean_luma)


def _load_real_crop(image_path: Path, crop_size: int = 224) -> tuple[np.ndarray, int] | None:
    """Load a real image and return a random 224x224 crop with heuristic label."""
    img = cv2.imread(str(image_path))
    if img is None:
        return None
    h, w = img.shape[:2]
    if h <= crop_size or w <= crop_size:
        img = cv2.resize(img, (crop_size, crop_size))
    else:
        y = random.randint(0, h - crop_size)
        x = random.randint(0, w - crop_size)
        img = img[y:y + crop_size, x:x + crop_size]

    small = cv2.resize(img, (160, 90))
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
    green_ratio = float((green > 0).mean())
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 80, 180)
    edge_density = float((edges > 0).mean())
    mean_luma = float(gray.mean())
    label = _heuristic_label(green_ratio, edge_density, mean_luma)
    return img, label


class GameFrameDataset(torch.utils.data.Dataset):
    """On-the-fly synthetic dataset with random real-image crops."""

    def __init__(
        self,
        synthetic_size: int = 600,
        real_images: list[Path] | None = None,
        real_crops: int = 120,
        dark_uniform: int = 40,
        augment: bool = True,
    ):
        self.synthetic_size = synthetic_size
        self.real_images = real_images or []
        self.real_crops = real_crops
        self.dark_uniform = dark_uniform
        self.augment = augment
        self.targets = [random.choice([0, 1, 2]) for _ in range(synthetic_size)]

    def __len__(self) -> int:
        return self.synthetic_size + self.real_crops + self.dark_uniform

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        if idx < self.synthetic_size:
            target = self.targets[idx]
            img, label = _synthetic_frame(target)
        elif idx < self.synthetic_size + self.real_crops:
            real_idx = (idx - self.synthetic_size) % max(1, len(self.real_images))
            if self.real_images:
                loaded = _load_real_crop(self.real_images[real_idx])
                if loaded is not None:
                    img, label = loaded
                else:
                    img, label = _synthetic_frame(random.choice([0, 1, 2]))
            else:
                img, label = _synthetic_frame(random.choice([0, 1, 2]))
        else:
            # Uniform dark menu samples.
            val = random.randint(2, 18)
            img = np.full((224, 224, 3), (val, val, val), dtype=np.uint8)
            label = 2

        if self.augment and random.random() > 0.5:
            img = cv2.flip(img, 1)

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        tensor = torch.from_numpy(rgb).permute(2, 0, 1)

        if self.augment:
            jitter = T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05)
            tensor = jitter(tensor)

        return tensor, label


class NormalizedModel(nn.Module):
    """Wraps a base classifier with ImageNet normalization baked in."""

    def __init__(self, base: nn.Module):
        super().__init__()
        self.register_buffer("mean", torch.from_numpy(IMAGENET_MEAN))
        self.register_buffer("std", torch.from_numpy(IMAGENET_STD))
        self.base = base

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.base((x - self.mean) / self.std)


def _build_model(num_classes: int = 3) -> nn.Module:
    base = mobilenet_v2(weights=MobileNet_V2_Weights.DEFAULT)
    # Freeze the entire backbone; train only a small MLP head. This keeps
    # the generic ImageNet features intact and avoids overfitting to a
    # small, synthetic dataset.
    for param in base.features.parameters():
        param.requires_grad = False
    base.classifier = nn.Sequential(
        nn.Dropout(0.3),
        nn.Linear(base.last_channel, 256),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(256, num_classes),
    )
    return NormalizedModel(base)


def _train(model: nn.Module, train_loader: torch.utils.data.DataLoader, val_loader: torch.utils.data.DataLoader, epochs: int, lr: float, device: str, class_weights: torch.Tensor | None = None) -> nn.Module:
    model = model.to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights.to(device) if class_weights is not None else None)
    optimizer = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=lr)
    best_acc = 0.0
    best_state = None

    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            out = model(x)
            loss = criterion(out, y)
            loss.backward()
            optimizer.step()
            running_loss += float(loss.item())

        model.eval()
        correct = 0
        total = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                out = model(x)
                preds = out.argmax(dim=1)
                correct += int((preds == y).sum().item())
                total += y.size(0)
        acc = correct / total if total else 0.0
        log.info(f"epoch {epoch + 1}/{epochs}  loss={running_loss / len(train_loader):.3f}  val_acc={acc:.3f}")
        if acc > best_acc:
            best_acc = acc
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}

    if best_state:
        model.load_state_dict(best_state)
    return model


def _export_onnx(model: nn.Module, out_path: Path) -> None:
    model.eval()
    dummy = torch.randn(1, 3, 224, 224)
    torch.onnx.export(
        model,
        dummy,
        str(out_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=11,
        dynamo=False,
    )
    log.info(f"ONNX exported to {out_path}")


def _benchmark(onnx_path: Path, device: str | None = None) -> dict[str, Any]:
    import onnxruntime as ort

    sess = ort.InferenceSession(str(onnx_path), providers=[device or "CPUExecutionProvider"])
    inp = sess.get_inputs()[0]
    times = []
    for _ in range(50):
        dummy = np.random.randn(1, 3, 224, 224).astype(np.float32)
        t0 = time.perf_counter()
        sess.run(None, {inp.name: dummy})
        times.append((time.perf_counter() - t0) * 1000)
    p50 = float(np.percentile(times, 50))
    p95 = float(np.percentile(times, 95))
    return {"p50_ms": p50, "p95_ms": p95, "samples": len(times)}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Distill Qoresence local VLM")
    parser.add_argument("--output", default="models/qoresence-vlm-distilled.onnx", type=Path)
    parser.add_argument("--size", default=350, type=int, help="synthetic training samples")
    parser.add_argument("--epochs", default=6, type=int)
    parser.add_argument("--lr", default=0.0005, type=float)
    parser.add_argument("--real", default="logs/eye_verify.jpg", type=Path)
    parser.add_argument("--batch", default=32, type=int)
    args = parser.parse_args()

    real_images = [Path(p) for p in [args.real, "logs/eye_check_19405562000000.png"] if Path(p).exists()]
    log.info(f"real anchors: {real_images}")

    train_set = GameFrameDataset(synthetic_size=args.size, real_images=real_images, real_crops=60, dark_uniform=150, augment=True)
    val_set = GameFrameDataset(synthetic_size=max(120, args.size // 3), real_images=[], real_crops=0, dark_uniform=40, augment=False)

    train_loader = torch.utils.data.DataLoader(train_set, batch_size=args.batch, shuffle=True, num_workers=0)
    val_loader = torch.utils.data.DataLoader(val_set, batch_size=args.batch, shuffle=False, num_workers=0)

    device = "cpu"
    # Approximate class weights based on the dataset mix (synthetic 350 balanced,
    # real crops ~60 football, dark uniform 150 menu).
    class_weights = torch.tensor([0.75, 1.35, 1.35], dtype=torch.float32)
    model = _build_model(num_classes=3)
    model = _train(model, train_loader, val_loader, args.epochs, args.lr, device, class_weights=class_weights)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    _export_onnx(model, args.output)

    bench = _benchmark(args.output)
    log.info(f"ONNX benchmark: {bench}")

    # Probe on real images
    client = LocalVLMClient(model_path=str(args.output))
    for p in real_images + [Path("logs/eye_verify.jpg")]:
        img = cv2.imread(str(p))
        if img is None:
            continue
        ctx = client.analyze_frame(img, game_profile="ncaa_football_27")
        log.info(f"probe {p}: {ctx.game_category.value} / {ctx.game_state.value} conf={ctx.confidence:.2f} mode={client.get_stats()['mode']}")

    # Probe on dark menu frame
    dark = np.zeros((720, 1280, 3), dtype=np.uint8)
    dark[:, :] = 10
    ctx = client.analyze_frame(dark, game_profile="ncaa_football_27")
    log.info(f"probe dark: {ctx.game_category.value} / {ctx.game_state.value} conf={ctx.confidence:.2f}")

    summary = {"model": str(args.output), "benchmark_ms": bench, "mode": client.get_stats()["mode"]}
    log.info(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
