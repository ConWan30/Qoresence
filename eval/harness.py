"""QoresenceScoreboard Bench — accuracy harness (no heavy deps)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class BenchResult:
    total: int
    cat_acc: float
    title_acc: float
    football_f1: float
    latency_p50_ms: float
    latency_p95_ms: float


def _load_dataset(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "samples" in data:
        return data["samples"]
    return data if isinstance(data, list) else []


def evaluate(predict_fn, dataset_path: str | Path = "eval/scoreboard_bench.json") -> BenchResult:
    path = Path(dataset_path)
    samples = _load_dataset(path)
    if not samples:
        return BenchResult(0, 0, 0, 0, 0, 0)
    lat = []
    cat_ok = title_ok = fb_ok = fb_total = 0
    for s in samples:
        exp = s.get("expected", s)
        exp_cat = str(exp.get("game_category", "") or exp.get("category", "")).lower()
        exp_title = str(exp.get("game_title", "") or "").lower()
        # call predictor with stub frame if provided, else direct dict
        t0 = time.perf_counter()
        try:
            pred = predict_fn(s)
        except Exception:
            pred = {}
        lat.append((time.perf_counter() - t0) * 1000)
        if isinstance(pred, dict):
            pc = str(pred.get("game_category", "") or pred.get("category", "")).lower()
            pt = str(pred.get("game_title", "") or "").lower()
        else:
            pc = str(getattr(pred, "game_category", "") or getattr(pred, "category", "")).lower()
            pt = str(getattr(pred, "game_title", "") or "").lower()
        if pc and pc == exp_cat:
            cat_ok += 1
        if pt and exp_title and pt == exp_title:
            title_ok += 1
        # football fields
        if exp_cat == "football":
            fb_total += 1
            if isinstance(pred, dict):
                hs_ok = pred.get("home_score") == exp.get("home_score")
                aw_ok = pred.get("away_score") == exp.get("away_score")
                if hs_ok and aw_ok:
                    fb_ok += 1
    lat.sort()
    n = len(samples)
    p50 = lat[n // 2] if lat else 0
    p95 = lat[int(n * 0.95)] if lat else 0
    return BenchResult(
        n, cat_ok / max(1, n), title_ok / max(1, n), fb_ok / max(1, fb_total), p50, p95
    )


def mock_predict(sample: dict) -> dict:
    exp = sample.get("expected", sample)
    return {
        "game_category": exp.get("game_category", "football"),
        "game_title": exp.get("game_title", "NCAA Football 27"),
        "home_score": exp.get("home_score"),
        "away_score": exp.get("away_score"),
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="eval/scoreboard_bench.json")
    ap.add_argument("--model", default="mock", choices=["mock", "local", "cloud"])
    args = ap.parse_args()
    fn = mock_predict
    if args.model == "local":
        try:
            import numpy as np

            from qoresence.vision.local_vlm import LocalVLMClient

            c = LocalVLMClient()

            def fn(s):
                # synthetic frame from hash
                img = np.zeros((90, 160, 3), dtype=np.uint8)
                return c.analyze_frame(img).__dict__ if c.analyze_frame(img) else {}
        except Exception as e:
            print(f"local fallback mock: {e}")
            fn = mock_predict
    r = evaluate(fn, args.dataset)
    print(json.dumps(r.__dict__, indent=2))
