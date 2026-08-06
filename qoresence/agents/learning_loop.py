"""Closed learning loop — anonymized logger + trainer.

Opt-in: only frame_hash + situation + moment label, never raw frames.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)
DEFAULT_LOG = Path("logs/learning_samples.jsonl")
DEFAULT_MODEL = Path("models/clip_worthiness.json")


@dataclass
class LearningSample:
    ts_ns: int
    situation: dict[str, Any]
    scored_moment: dict[str, Any]
    label: float | None = None  # 1=engaging clip, 0=skip
    frame_hash: str = ""
    wp_swing: float = 0.0


class LearningLogger:
    def __init__(self, path: Path | str | None = None):
        self.path = Path(path) if path else DEFAULT_LOG
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, state: Any, moment: Any, label: float | None = None, frame_hash: str = "", wp_swing: float = 0.0) -> None:
        # coerce state/moment to dict
        def _to_dict(x):
            if x is None:
                return {}
            if isinstance(x, dict):
                return x
            if hasattr(x, "to_dict"):
                try:
                    return x.to_dict()
                except Exception:
                    pass
            return {"repr": str(x)[:500]}
        s = LearningSample(
            ts_ns=time.time_ns(),
            situation=_to_dict(state),
            scored_moment=_to_dict(moment),
            label=label,
            frame_hash=frame_hash[:16] if frame_hash else "",
            wp_swing=wp_swing,
        )
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(s)) + "\n")
        except Exception as e:
            log.warning(f"LearningLogger write failed: {e}")

    def load_all(self) -> list[LearningSample]:
        if not self.path.exists():
            return []
        out = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    out.append(LearningSample(**d))
                except Exception:
                    continue
        return out

    def flush(self) -> None:
        pass


class ClipWorthinessTrainer:
    """Logistic regression on learning_samples -> models/clip_worthiness.json"""
    def __init__(self, model_path: Path | str | None = None):
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL

    def _featurize(self, s: LearningSample) -> list[float]:
        sit = s.situation
        # features: wp_swing, red_zone, close_game, apm
        pos = str(sit.get("field_position") or "")
        is_rz = 1.0 if "opp" in pos.lower() and any(f"opp {i}" in pos.lower() for i in range(1, 21)) or "opp 1" in pos.lower() else 0.0
        # simpler: check wp_swing driven
        if "opp" in pos.lower():
            try:
                import re
                m = re.search(r"opp(?:onent)?\s*(\d+)", pos.lower())
                is_rz = 1.0 if m and int(m.group(1)) <= 20 else 0.0
            except Exception:
                pass
        hs = sit.get("home_score"); aw = sit.get("away_score")
        try:
            margin = abs(int(hs or 0) - int(aw or 0)) if hs is not None and aw is not None else 10
        except Exception:
            margin = 10
        close = 1.0 if margin <= 8 else 0.0
        apm = float(sit.get("controller", {}).get("apm_5s", 0) if isinstance(sit.get("controller"), dict) else 0)
        apm_n = min(1.0, apm / 120.0)
        return [float(s.wp_swing), is_rz, close, apm_n]

    def train_from_logger(self, logger: LearningLogger, lr: float = 0.5, iters: int = 300, l2: float = 0.01) -> dict:
        samples = [s for s in logger.load_all() if s.label is not None]
        if len(samples) < 10:
            raise ValueError(f"Need >=10 labeled samples, got {len(samples)}")
        X = np.array([self._featurize(s) for s in samples], dtype=float)
        y = np.array([float(s.label) for s in samples], dtype=float)
        # add bias
        N, D = X.shape
        w = np.zeros(D); b = 0.0
        def sig(x): return 1/(1+np.exp(-np.clip(x,-20,20)))
        for _ in range(iters):
            logits = X @ w + b
            p = sig(logits)
            err = p - y
            gw = X.T @ err / N + l2 * w
            gb = err.mean()
            w -= lr * gw; b -= lr * gb
        weights = {"wp_swing": float(w[0]), "red_zone": float(w[1]), "close_game": float(w[2]), "apm": float(w[3]), "bias": float(b)}
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, "w", encoding="utf-8") as f:
            json.dump(weights, f, indent=2)
        log.info(f"ClipWorthinessTrainer saved {weights} -> {self.model_path}")
        return weights


def create_learning_logger(path: str | Path | None = None) -> LearningLogger:
    return LearningLogger(path=path)
