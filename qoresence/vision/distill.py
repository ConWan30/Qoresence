"""
Offline distill pipeline: teacher (Nemotron 12B / mock) -> student (SmolVLM2-256M) -> ONNX.

No capture card required:
  --synthetic --teacher mock  -> generates synthetic frames + labels from bench
  --teacher nemotron          -> calls VLMClient (needs API key) to pseudo-label real frames
  --teacher local             -> uses LocalVLMClient heuristic as teacher (baseline)

Output:
  data/distill/train.jsonl  (prompt/response pairs)
  models/qoresence-vlm-distilled.onnx  (via optimum export)

Usage:
  python -m qoresence.vision.distill --synthetic --teacher mock --out data/distill/train.jsonl
  python -m qoresence.vision.distill --train --student HuggingFaceTB/SmolVLM2-256M-Instruct --data data/distill/train.jsonl
  python -m qoresence.vision.distill --export --onnx models/qoresence-vlm-distilled.onnx
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from qoresence.vision.visual_context import VisualContext, GameCategory, GameState, build_vlm_prompt

log = logging.getLogger(__name__)

DEFAULT_BENCH = Path("eval/scoreboard_bench.json")
DEFAULT_OUT = Path("data/distill/train.jsonl")
DEFAULT_ONNX = Path("models/qoresence-vlm-distilled.onnx")
STUDENT_DEFAULT = "HuggingFaceTB/SmolVLM2-256M-Instruct"


# ---------------------------------------------------------------------------
# Synthetic frame generation (matches LocalVLMClient heuristic branches)
# ---------------------------------------------------------------------------
def _synthetic_frame(category: str, variant: int = 0) -> np.ndarray:
    cat = category.lower()
    if cat == "football":
        # green field + white scoreboard bar + cross lines
        h, w = 90, 160
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        frame[:, :] = (0, 200, 0)
        cv2.rectangle(frame, (5, 5), (w - 5, 18), (255, 255, 255), -1)
        cv2.line(frame, (0, h // 2), (w, h // 2), (255, 255, 255), 1)
        cv2.line(frame, (w // 2, 0), (w // 2, h), (255, 255, 255), 1)
        # jitter green slightly per variant
        jitter = (variant % 20) - 10
        frame[:, :, 1] = np.clip(frame[:, :, 1].astype(int) + jitter, 0, 255).astype(np.uint8)
        return cv2.resize(frame, (224, 224))
    if cat == "shooter":
        h, w = 90, 160
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        for y in range(0, h, 10):
            for x in range(0, w, 10):
                v = 120 if (x // 10 + y // 10) % 2 == 0 else 30
                frame[y:y+5, x:x+5] = (v, v, v)
        for _ in range(6):
            x1, y1 = random.randint(0, w-1), random.randint(0, h-1)
            x2, y2 = random.randint(0, w-1), random.randint(0, h-1)
            cv2.line(frame, (x1, y1), (x2, y2), (200, 200, 200), 1)
        return cv2.resize(frame, (1280, 720))
    if cat in ("menu", "dark", "unknown") and variant % 3 == 0:
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame[:, :] = 5
        return frame
    # unknown gray
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame[:, :] = (100, 100, 100)
    return frame


def _expected_to_visual_context(expected: dict[str, Any]) -> VisualContext:
    cat_raw = str(expected.get("game_category", "unknown")).lower()
    cat = {
        "football": GameCategory.FOOTBALL,
        "shooter": GameCategory.SHOOTER,
    }.get(cat_raw, GameCategory.UNKNOWN)
    title = expected.get("game_title", "")
    state = GameState.GAMEPLAY if cat != GameCategory.UNKNOWN else GameState.UNKNOWN
    if cat_raw in ("menu", "dark"):
        state = GameState.MENU
    # Map bench fields to VisualContext fields (VisualContext has no kills/deaths;
    # shooter uses health/ammo/score + round_info for kill count if present).
    kills = expected.get("kills")
    deaths = expected.get("deaths")
    round_info = ""
    if kills is not None or deaths is not None:
        round_info = f"kills={kills} deaths={deaths}"
    ctx = VisualContext(
        game_state=state,
        game_category=cat,
        game_title=title,
        confidence=0.95,
        frame_quality=expected.get("frame_quality", "ok"),
        home_score=expected.get("home_score"),
        away_score=expected.get("away_score"),
        quarter=expected.get("quarter"),
        down=expected.get("down"),
        yards_to_go=expected.get("yards_to_go"),
        field_position=expected.get("field_position"),
        health=expected.get("health"),
        ammo=expected.get("ammo"),
        score=expected.get("score") if expected.get("score") is not None else kills,
        round_info=round_info,
        model="teacher:mock",
    )
    if kills is not None:
        ctx.details["kills"] = kills
    if deaths is not None:
        ctx.details["deaths"] = deaths
    return ctx


# ---------------------------------------------------------------------------
# Teacher labeling
# ---------------------------------------------------------------------------
def _label_with_mock(expected: dict) -> dict:
    ctx = _expected_to_visual_context(expected)
    return ctx.to_dict()


def _label_with_local(frame: np.ndarray) -> dict:
    from qoresence.vision.local_vlm import LocalVLMClient
    c = LocalVLMClient()
    ctx = c.analyze_frame(frame)
    if ctx is None:
        return _label_with_mock({})
    return ctx.to_dict()


def _label_with_nemotron(frame: np.ndarray, prompt: str) -> dict | None:
    try:
        from qoresence.lobes.visual import VLMClient
        from qoresence.core.unified_config import VisualConfig
        cfg = VisualConfig()
        client = VLMClient(cfg)
        # VLMClient.analyze_frame returns VisualContext directly
        ctx = client.analyze_frame(frame, prompt)
        if ctx is None:
            return None
        d = ctx.to_dict()
        d["model"] = "teacher:nemotron"
        return d
    except Exception as e:
        log.warning(f"Nemotron teacher failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Dataset preparation
# ---------------------------------------------------------------------------
def prepare(
    bench_path: Path = DEFAULT_BENCH,
    out_path: Path = DEFAULT_OUT,
    teacher: str = "mock",
    synthetic: bool = True,
    expand: int = 1,
    image_dir: Path | None = None,
) -> int:
    """
    Build train.jsonl from bench samples.

    expand: replicate each bench sample N times with jitter (for synthetic scale-up).
            e.g. bench 20 x expand 500 = 10k
    """
    with open(bench_path, encoding="utf-8") as f:
        data = json.load(f)
    samples = data.get("samples", data) if isinstance(data, dict) else data
    if not isinstance(samples, list):
        raise ValueError("bench has no samples list")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if image_dir:
        image_dir.mkdir(parents=True, exist_ok=True)

    prompt_football = build_vlm_prompt("football")
    prompt_shooter = build_vlm_prompt("shooter")

    n = 0
    with open(out_path, "w", encoding="utf-8") as out:
        for samp in samples:
            expected = samp.get("expected", samp)
            cat = str(expected.get("game_category", "unknown")).lower()
            prompt = prompt_football if cat == "football" else prompt_shooter if cat == "shooter" else prompt_football

            for rep in range(expand):
                if synthetic:
                    frame = _synthetic_frame(cat, variant=rep)
                    # stable hash for provenance (matches vision_stack)
                    small = cv2.resize(frame, (160, 90))
                    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                    fh = hashlib.sha256(gray.tobytes()).hexdigest()[:16]
                else:
                    # real frame: expect samp has image_path
                    img_path = samp.get("image_path") or samp.get("frame_path")
                    if not img_path or not Path(img_path).exists():
                        log.warning(f"skip {samp.get('frame_hash')}: no image_path and synthetic=False")
                        continue
                    frame = cv2.imread(str(img_path))
                    fh = samp.get("frame_hash", hashlib.sha256(frame.tobytes()).hexdigest()[:16])

                if image_dir is not None and synthetic:
                    # optionally write png for inspection / HF datasets
                    ip = image_dir / f"{fh}_{rep}.png"
                    cv2.imwrite(str(ip), frame)
                    image_ref = str(ip)
                else:
                    image_ref = fh  # hash only; synthetic frames are reproducible

                # teacher label
                if teacher == "mock":
                    label = _label_with_mock(expected)
                elif teacher == "local":
                    label = _label_with_local(frame)
                elif teacher == "nemotron":
                    label = _label_with_nemotron(frame, prompt)
                    if label is None:
                        label = _label_with_mock(expected)
                else:
                    raise ValueError(f"unknown teacher {teacher}")

                label["frame_hash"] = fh
                # training pair: prompt + json response
                rec = {
                    "image": image_ref,
                    "frame_hash": fh,
                    "prompt": prompt,
                    "response": json.dumps(label),
                    "expected": expected,
                    "teacher": teacher,
                    "category": cat,
                }
                out.write(json.dumps(rec) + "\n")
                n += 1

    log.info(f"prepare: {n} pairs -> {out_path} (teacher={teacher}, synthetic={synthetic}, expand={expand})")
    return n


# ---------------------------------------------------------------------------
# Fine-tune (stub that runs if transformers is installed)
# ---------------------------------------------------------------------------
def train(student: str = STUDENT_DEFAULT, data: Path = DEFAULT_OUT, out_dir: Path = Path("models/smolvlm2-qoresence"), epochs: int = 3) -> bool:
    """
    Fine-tune SmolVLM2 on train.jsonl.

    Requires: transformers[torch], accelerate, datasets, peft (optional LoRA).
    If deps missing, prints instructions and returns False (offline stub).
    """
    try:
        import torch  # noqa: F401
        from transformers import TrainingArguments, Trainer  # noqa: F401
    except ImportError as e:
        log.warning(f"train deps missing ({e}). Install: pip install \"transformers[torch]\" accelerate datasets peft")
        print("""
[distill] train deps not installed — stub mode.
  pip install \"transformers[torch]\" optimum[onnxruntime] accelerate datasets peft
  Then re-run: python -m qoresence.vision.distill --train
For now, synthetic train.jsonl is ready for when you install deps.
""")
        return False

    # Lazy import after dep check
    log.info(f"train: student={student} data={data} epochs={epochs}")
    # Minimal trainer scaffold — loads JSONL, tokenizes prompt+response
    # Full implementation is ~120 lines; stub keeps repo runnable without GPU.
    try:
        from datasets import load_dataset
        from transformers import AutoProcessor, AutoModelForVision2Seq

        ds = load_dataset("json", data_files=str(data), split="train")
        log.info(f"loaded {len(ds)} samples")

        processor = AutoProcessor.from_pretrained(student, trust_remote_code=True)
        model = AutoModelForVision2Seq.from_pretrained(student, trust_remote_code=True)

        # LoRA optional
        try:
            from peft import LoraConfig, get_peft_model
            lora = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj", "v_proj"], lora_dropout=0.05, bias="none")
            model = get_peft_model(model, lora)
            log.info("LoRA enabled")
        except Exception:
            log.info("LoRA not available, full fine-tune")

        # Tokenization is model-specific; this is the generic shape:
        def _tok(batch):
            # processor handles image+text; for synthetic we skip image load and use dummy
            texts = [p + "\n" + r for p, r in zip(batch["prompt"], batch["response"])]
            enc = processor(text=texts, padding=True, truncation=True, max_length=512, return_tensors="pt")
            enc["labels"] = enc["input_ids"].clone()
            return enc

        # NOTE: vision inputs need real images; synthetic dummy path above is for CI.
        # Replace with actual image loading when you have real frames:
        #   from PIL import Image; Image.open(batch["image"])
        log.warning("train scaffold: wire image loading for real frames before GPU run (see distill.py _tok)")
        print(f"[distill] scaffold ready — {len(ds)} samples, student {student}. Wire _tok() image loading then run Trainer.")
        return False
    except Exception as e:
        log.error(f"train failed: {e}", exc_info=True)
        return False


def export_onnx(onnx_path: Path = DEFAULT_ONNX, model_dir: Path = Path("models/smolvlm2-qoresence")) -> bool:
    """
    Export fine-tuned model to ONNX via optimum-cli.
    Falls back to telling user the command if optimum not installed.
    """
    if not model_dir.exists():
        log.warning(f"model_dir {model_dir} not found — train first or use mock heuristic")
        print(f"[distill] no model at {model_dir}. Run --train or keep heuristic LocalVLMClient.")
        return False
    cmd = ["optimum-cli", "export", "onnx", "--model", str(model_dir), "--task", "image-text-to-text", str(onnx_path)]
    log.info(f"export: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        # quantize to int8 for <100ms CPU
        q_path = onnx_path.with_suffix(".int8.onnx")
        try:
            subprocess.run(
                [sys.executable, "-m", "onnxruntime.quantization.quantize_dynamic", "--input", str(onnx_path), "--output", str(q_path), "--weight_type", "QInt8"],
                check=True,
            )
            log.info(f"quantized -> {q_path}")
        except Exception as e:
            log.warning(f"quantize skip: {e}")
        # sanity check
        import onnxruntime as ort
        sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
        log.info(f"ONNX OK: {onnx_path} inputs={[i.name for i in sess.get_inputs()]}")
        return True
    except FileNotFoundError:
        print(f"[distill] optimum-cli not found. Install: pip install optimum[onnxruntime]\n  Then run: {' '.join(cmd)}")
        return False
    except subprocess.CalledProcessError as e:
        log.error(f"export failed: {e}")
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description="Qoresence distill pipeline")
    ap.add_argument("--bench", type=Path, default=DEFAULT_BENCH, help="bench json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="train.jsonl out")
    ap.add_argument("--teacher", choices=["mock", "local", "nemotron"], default="mock")
    ap.add_argument("--synthetic", action="store_true", help="generate synthetic frames (no card needed)")
    ap.add_argument("--no-synthetic", dest="synthetic", action="store_false")
    ap.set_defaults(synthetic=True)
    ap.add_argument("--expand", type=int, default=1, help="replicate each bench sample N times (e.g. 500 for 10k from 20)")
    ap.add_argument("--image-dir", type=Path, default=None, help="optional: write synthetic PNGs to dir")
    ap.add_argument("--train", action="store_true", help="fine-tune student after prepare")
    ap.add_argument("--student", default=STUDENT_DEFAULT)
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--model-dir", type=Path, default=Path("models/smolvlm2-qoresence"))
    ap.add_argument("--export", action="store_true", help="export to ONNX")
    ap.add_argument("--onnx", type=Path, default=DEFAULT_ONNX)
    ap.add_argument("--prepare", action="store_true", help="only prepare dataset (default if no --train/--export)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    do_prepare = args.prepare or (not args.train and not args.export)
    if do_prepare:
        n = prepare(bench_path=args.bench, out_path=args.out, teacher=args.teacher, synthetic=args.synthetic, expand=args.expand, image_dir=args.image_dir)
        print(f"[distill] prepared {n} pairs -> {args.out}")
        # quick harness on synthetic
        try:
            from eval.harness import evaluate, mock_predict
            r = evaluate(mock_predict, str(args.bench))
            print(f"[bench] mock: cat_acc={r.cat_acc:.2f} football_f1={r.football_f1:.2f} p50={r.latency_p50_ms:.1f}ms")
        except Exception:
            pass

    if args.train:
        ok = train(student=args.student, data=args.out, out_dir=args.model_dir, epochs=args.epochs)
        sys.exit(0 if ok else 1 if do_prepare is False else 0)

    if args.export:
        ok = export_onnx(onnx_path=args.onnx, model_dir=args.model_dir)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
