"""
Qoresence Presence Fusion Engine — Phase 6 + Real Fusion Upgrade

Consumes events from RetinaEventBus, produces PresenceReport with
presence_sync_ok and weighted verdict across all lobes.

Real Fusion upgrade adds:
- CouplingAnalyzer (50 ms binned cross-correlation)
- Learned weights loader / logistic calibration
- Sigmoid confidence calibration
- Coupling stats surfaced in report details
"""

from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from qoresence.core import (
    EventType,
    RetinaEventBus,
    RetinaUnifiedConfig,
    SourceLobe,
    clock_ns,
)

log = logging.getLogger(__name__)

DEFAULT_WEIGHTS_PATH = Path("models/fusion_weights.json")
BUCKET_MS = 50.0
BUCKET_NS = int(BUCKET_MS * 1_000_000)  # 50_000_000 ns


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    """Numerically stable sigmoid."""
    x = np.clip(x, -20, 20)
    return 1.0 / (1.0 + np.exp(-x))


# ──────────────────────────────────────────────────────────────────────────────
# COUPLING ANALYZER
# ──────────────────────────────────────────────────────────────────────────────


class CouplingAnalyzer:
    """
    Cross-correlation between controller trigger_onset timestamps and screen
    cv_motion spikes.

    Signal processing:
    - Bin events into 50 ms buckets over a sliding window (default 5 s)
    - Controller stream: binary spike per bucket (1 if trigger_onset else 0)
    - Screen stream: binary spike per bucket if motion_val > threshold else 0
      (also stores max motion magnitude for continuous variant)
    - Compute normalized cross-correlation via numpy.correlate on
      zero-mean / unit-variance signals
    - Peak lag gives best alignment (ms), coupling_score is peak correlation
      clamped 0-1, negative_control uses shuffled surrogate,
      decoupled_energy = 1 - coupling_score.
    """

    def __init__(
        self,
        bucket_ms: float = BUCKET_MS,
        motion_threshold: float = 0.01,
        max_history_s: float = 60.0,
    ):
        self.bucket_ms = bucket_ms
        self.bucket_ns = int(bucket_ms * 1_000_000)
        self.motion_threshold = motion_threshold
        self.max_history_s = max_history_s

        self._controller_ns: list[int] = []
        self._motion_samples: list[tuple[int, float]] = []  # (ns, motion_val)

        # last computed cache
        self._last_result: dict[str, float] = {
            "coupling_score": 0.0,
            "best_lag_ms": 0.0,
            "negative_control": 0.0,
            "decoupled_energy": 1.0,
        }

    # ── ingestion ────────────────────────────────────────────────────────────

    def add_controller_event(self, ns: int) -> None:
        """Record a controller trigger_onset at clock ns."""
        self._controller_ns.append(int(ns))
        self._prune_history()

    def add_motion_sample(self, ns: int, motion_val: float) -> None:
        """Record a screen cv_motion sample. Only spikes above threshold binarized."""
        self._motion_samples.append((int(ns), float(motion_val)))
        self._prune_history()

    def _prune_history(self) -> None:
        """Keep only max_history_s of data to bound memory."""
        if not self._controller_ns and not self._motion_samples:
            return
        # find latest timestamp
        latest = 0
        if self._controller_ns:
            latest = max(latest, self._controller_ns[-1])
        if self._motion_samples:
            latest = max(latest, self._motion_samples[-1][0])
        cutoff = latest - int(self.max_history_s * 1e9)
        # prune controller
        if self._controller_ns:
            # controller list is append-ordered monotonic typically
            idx = 0
            for i, ns in enumerate(self._controller_ns):
                if ns >= cutoff:
                    idx = i
                    break
            else:
                idx = len(self._controller_ns)
            if idx > 0:
                self._controller_ns = self._controller_ns[idx:]
        # prune motion
        if self._motion_samples:
            idx = 0
            for i, (ns, _) in enumerate(self._motion_samples):
                if ns >= cutoff:
                    idx = i
                    break
            else:
                idx = len(self._motion_samples)
            if idx > 0:
                self._motion_samples = self._motion_samples[idx:]

    # ── computation ──────────────────────────────────────────────────────────

    def compute_coupling(self, window_s: float = 5.0) -> dict[str, float]:
        """
        Compute coupling over the trailing window_s seconds.

        Returns dict with:
          coupling_score  0-1  (peak normalized cross-correlation, positive)
          best_lag_ms     float  (lag of peak, positive = motion lags controller)
          negative_control 0-1 (shuffled surrogate peak)
          decoupled_energy 0-1 (1 - coupling_score, energy not explained)
        """
        if window_s <= 0:
            return dict(self._last_result)

        # collect window
        latest = 0
        if self._controller_ns:
            latest = max(latest, self._controller_ns[-1])
        if self._motion_samples:
            latest = max(latest, self._motion_samples[-1][0])
        if latest == 0:
            # no data yet
            return dict(self._last_result)

        window_ns = int(window_s * 1e9)
        start_ns = latest - window_ns

        # filter to window
        ctrl_window = [ns for ns in self._controller_ns if ns >= start_ns]
        motion_window = [(ns, v) for ns, v in self._motion_samples if ns >= start_ns]

        n_buckets = int(window_s * 1000 / self.bucket_ms)  # e.g. 5s/50ms = 100
        if n_buckets < 4:
            n_buckets = 4

        # edge: not enough spikes
        if len(ctrl_window) < 1 and len(motion_window) < 1:
            return dict(self._last_result)
        # if either stream empty, coupling is 0
        if len(ctrl_window) == 0 or len(motion_window) == 0:
            result = {
                "coupling_score": 0.0,
                "best_lag_ms": 0.0,
                "negative_control": 0.0,
                "decoupled_energy": 1.0,
            }
            self._last_result = result
            return dict(result)

        # bin into buckets
        bins_c = np.zeros(n_buckets, dtype=np.float64)
        bins_m = np.zeros(n_buckets, dtype=np.float64)

        for ns in ctrl_window:
            idx = int((ns - start_ns) // self.bucket_ns)
            if 0 <= idx < n_buckets:
                bins_c[idx] = 1.0  # binary spike (cap at 1)

        for ns, val in motion_window:
            idx = int((ns - start_ns) // self.bucket_ns)
            if 0 <= idx < n_buckets:
                # binarize on threshold: spike if val > threshold
                if val > self.motion_threshold:
                    bins_m[idx] = 1.0
                else:
                    # still record continuous magnitude as fallback if many low values
                    # we keep binary for correlation clarity: low motion = 0
                    pass
                # alternative continuous: bins_m[idx] = max(bins_m[idx], min(1.0, val*2))
                # keep binary for now

        # need variance in both signals
        std_c = bins_c.std()
        std_m = bins_m.std()
        if std_c < 1e-9 or std_m < 1e-9:
            result = {
                "coupling_score": 0.0,
                "best_lag_ms": 0.0,
                "negative_control": 0.0,
                "decoupled_energy": 1.0,
            }
            self._last_result = result
            return dict(result)

        # normalize to zero-mean, unit-variance
        c_norm = (bins_c - bins_c.mean()) / (std_c + 1e-9)
        m_norm = (bins_m - bins_m.mean()) / (std_m + 1e-9)

        # normalized cross-correlation via numpy.correlate
        # correlate c_norm with m_norm, mode full => length 2*N-1
        corr = np.correlate(c_norm, m_norm, mode="full") / n_buckets
        # corr values are in approx -1..1 (pearson at each lag when normalized /N)

        # find peak positive correlation
        peak_idx = int(np.argmax(corr))
        peak_val = float(corr[peak_idx])
        # also consider absolute peak? spec says peak lag, coupling 0-1
        # clamp negative to 0 (no coupling)
        coupling_score = float(np.clip(peak_val, 0.0, 1.0))

        lag_buckets = peak_idx - (n_buckets - 1)
        best_lag_ms = float(lag_buckets * self.bucket_ms)

        # negative control: shuffle surrogate (deterministic RNG for reproducibility)
        rng = np.random.default_rng(0)
        m_shuffled = rng.permutation(m_norm)
        corr_shuf = np.correlate(c_norm, m_shuffled, mode="full") / n_buckets
        # negative control is max absolute shuffled correlation (or max positive)
        negative_control = float(np.clip(np.max(corr_shuf), 0.0, 1.0))
        # alternative: np.max(np.abs(corr_shuf)) but keep positive max

        decoupled_energy = float(np.clip(1.0 - coupling_score, 0.0, 1.0))

        result = {
            "coupling_score": round(coupling_score, 4),
            "best_lag_ms": round(best_lag_ms, 1),
            "negative_control": round(negative_control, 4),
            "decoupled_energy": round(decoupled_energy, 4),
        }
        self._last_result = result
        return dict(result)

    def get_stats(self) -> dict[str, float]:
        """Return last computed stats (or recompute with default window)."""
        return dict(self._last_result)

    def reset(self) -> None:
        """Clear all history."""
        self._controller_ns.clear()
        self._motion_samples.clear()
        self._last_result = {
            "coupling_score": 0.0,
            "best_lag_ms": 0.0,
            "negative_control": 0.0,
            "decoupled_energy": 1.0,
        }


# ──────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class LobeContribution:
    """Contribution from a single lobe to the fused verdict."""

    lobe: SourceLobe
    weight: float
    score: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    last_event_ns: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    """Cross-lobe anomaly detection result."""

    type: str  # "temporal_desync" | "spatial_mismatch" | "missing_lobe" | "contradiction"
    severity: str  # "low" | "medium" | "high"
    description: str
    lobes_involved: list[SourceLobe]
    timestamp_ns: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PresenceReport:
    """Fused presence report output."""

    session_id: str
    clock_ns: int
    session_head_ns: int
    presence_sync_ok: bool
    weighted_verdict: str  # "present" | "likely_present" | "uncertain" | "absent"
    lobe_contributions: dict[str, float]  # lobe -> contribution score
    anomalies: list[Anomaly]
    confidence: float  # Overall confidence 0.0-1.0 (sigmoid calibrated)
    fusion_weights: dict[str, float]  # lobe -> weight used
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSONL/WebSocket."""
        return {
            "session_id": self.session_id,
            "clock_ns": self.clock_ns,
            "session_head_ns": self.session_head_ns,
            "presence_sync_ok": self.presence_sync_ok,
            "weighted_verdict": self.weighted_verdict,
            "lobe_contributions": self.lobe_contributions,
            "anomalies": [
                {
                    "type": a.type,
                    "severity": a.severity,
                    "description": a.description,
                    "lobes_involved": [lobe.value for lobe in a.lobes_involved],
                    "timestamp_ns": a.timestamp_ns,
                    "details": a.details,
                }
                for a in self.anomalies
            ],
            "confidence": self.confidence,
            "fusion_weights": self.fusion_weights,
            "details": self.details,
        }


# ──────────────────────────────────────────────────────────────────────────────
# VISUAL HYSTERESIS
# ──────────────────────────────────────────────────────────────────────────────


class VisualHysteresis:
    """Temporal majority smoothing for visual_context game_category/state.

    Reuses Phase 2 hysteresis logic: a category must appear ``min_agree``
    times in the last ``window`` frames before it is emitted. This prevents a
    single menu/replay frame from flipping the fused verdict, and also lets the
    active game profile suppress cross-game hallucinations (e.g. shooter frames
    when the configured profile is football).
    """

    def __init__(self, window: int = 5, min_agree: int = 3, profile_category: str = "football"):
        self._window = window
        self._min_agree = min_agree
        self._profile_category = profile_category
        self._history: deque[tuple[str, str, float]] = deque(maxlen=window)
        self._last_category: str = "unknown"
        self._last_state: str = "unknown"
        self._last_confidence: float = 0.0

    def _guard(self, category: str) -> str:
        """Profile-aware guard: football profile should never emit shooter."""
        if self._profile_category == "football" and category == "shooter":
            return "unknown"
        if self._profile_category == "shooter" and category == "football":
            return "unknown"
        return category

    def update(
        self, raw_category: str | None, raw_state: str | None, confidence: float
    ) -> tuple[str, str, float]:
        """Update with a fresh visual observation and return smoothed (category, state, confidence)."""
        category = str(raw_category).lower().strip() if raw_category else "unknown"
        state = str(raw_state).lower().strip() if raw_state else "unknown"

        # If category is gameplay-specific, normalize state to gameplay
        if category in ("football", "shooter"):
            state = "gameplay"

        # Apply profile guard. When the guard fires, treat the frame as unknown.
        guarded = self._guard(category)
        if guarded != category and guarded == "unknown":
            state = "unknown"
        category = guarded

        self._history.append((category, state, float(confidence)))

        # Count categories
        cat_counts: dict[str, int] = {}
        cat_confs: dict[str, float] = {}
        for c, _s, conf in self._history:
            cat_counts[c] = cat_counts.get(c, 0) + 1
            cat_confs[c] = cat_confs.get(c, 0.0) + conf

        # Find majority category that meets min_agree, preferring higher confidence tie-break
        winner: str | None = None
        for c in sorted(cat_counts, key=lambda x: (-cat_counts[x], -cat_confs[x])):
            if cat_counts[c] >= self._min_agree:
                winner = c
                break

        if winner is None:
            # No stable majority yet: hold previous smoothed output
            return self._last_category, self._last_state, self._last_confidence

        # Majority state and average confidence among winner entries
        winner_entries = [(s, conf) for c, s, conf in self._history if c == winner]
        state_counts: dict[str, int] = {}
        state_confs: dict[str, float] = {}
        for s, conf in winner_entries:
            state_counts[s] = state_counts.get(s, 0) + 1
            state_confs[s] = state_confs.get(s, 0.0) + conf
        majority_state = max(
            state_counts, key=lambda x: (state_counts[x], -state_confs.get(x, 0.0))
        )
        avg_conf = state_confs[majority_state] / max(state_counts[majority_state], 1)

        self._last_category = winner
        self._last_state = majority_state
        self._last_confidence = avg_conf
        return winner, majority_state, avg_conf

    def get_state(self) -> tuple[str, str, float]:
        """Return last smoothed state without updating."""
        return self._last_category, self._last_state, self._last_confidence


# ──────────────────────────────────────────────────────────────────────────────
# FUSION ENGINE
# ──────────────────────────────────────────────────────────────────────────────


class PresenceFusionEngine:
    """
    Fuses multi-lobe events into a unified presence verdict.

    Subscribes to RetinaEventBus, maintains per-lobe state,
    computes weighted verdict, detects anomalies.

    Real upgrades:
    - CouplingAnalyzer for controller↔screen correlation
    - Learned weights via logistic regression (numpy only)
    - Sigmoid confidence calibration
    """

    # canonical lobe order for weight vectors (used in calibration)
    LOBE_ORDER: list[SourceLobe] = [
        SourceLobe.STREAMER,
        SourceLobe.CONTROLLER,
        SourceLobe.SCREEN,
        SourceLobe.OUTCOME,
        SourceLobe.VISUAL,
    ]

    def __init__(
        self,
        config: RetinaUnifiedConfig,
        bus: RetinaEventBus,
    ):
        self.config = config
        self.bus = bus
        self.session_id = config.session_id
        self.session_head_ns = config.session_head_ns

        # Fusion weights from config
        self.weights: dict[SourceLobe, float] = {
            SourceLobe.STREAMER: config.fusion_weights.streamer_presence_sync,
            SourceLobe.CONTROLLER: config.fusion_weights.controller_causal_density,
            SourceLobe.SCREEN: config.fusion_weights.screen_coupling_score,
            SourceLobe.OUTCOME: config.fusion_weights.outcome_coherence,
            SourceLobe.VISUAL: config.fusion_weights.visual_confirmation,
        }

        # try learned weights override (non-breaking)
        self._try_load_learned_weights()

        # Per-lobe state
        self._lobe_state: dict[SourceLobe, dict[str, Any]] = defaultdict(dict)
        self._lobe_last_event_ns: dict[SourceLobe, int] = {}
        self._lobe_event_counts: dict[SourceLobe, int] = defaultdict(int)

        # Coupling analyzer
        self._coupling = CouplingAnalyzer()

        # VisualContext smoothing (Phase 5): reuse hysteresis, profile-aware guard
        self._profile_category = getattr(config.active_game_profile, "category", "football")
        self._visual_hysteresis = VisualHysteresis(
            window=5, min_agree=3, profile_category=self._profile_category
        )

        # Presence sync (from streamer)
        self._presence_sync_ok = False
        self._last_controller_sync_ns = 0

        # Anomalies
        self._anomalies: list[Anomaly] = []
        self._max_anomalies = 100

        # Thread safety
        self._lock = threading.RLock()

        # Subscribe to bus
        self._unsubscribe = bus.subscribe(self._on_event)

        # Report callback (optional)
        self._report_callback: Callable[[PresenceReport], None] | None = None

        # Emit session_start
        self._emit_report(force=True)

    # ── weights persistence ──────────────────────────────────────────────────

    def _try_load_learned_weights(self) -> None:
        """If models/fusion_weights.json exists, load it silently."""
        try:
            if DEFAULT_WEIGHTS_PATH.exists():
                self.load_weights(str(DEFAULT_WEIGHTS_PATH))
        except Exception as e:
            log.debug(f"Could not auto-load learned weights: {e}")

    def load_weights(self, path: str | Path) -> dict[str, float]:
        """
        Load JSON weights from path and apply to engine.

        Expected JSON: {"streamer":0.25, "controller":0.25, ...} or
        {"weights":{"streamer":...}} . Values are normalized to sum 1.
        Returns the applied weights dict.
        """
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        # unwrap if nested
        if "weights" in data and isinstance(data["weights"], dict):
            data = data["weights"]
        # map string keys to SourceLobe
        new_weights: dict[SourceLobe, float] = {}
        for lobe in self.LOBE_ORDER:
            key = lobe.value
            if key in data:
                new_weights[lobe] = float(data[key])
            else:
                new_weights[lobe] = self.weights.get(lobe, 0.0)
        # normalize to sum 1
        total = sum(new_weights.values())
        if total > 0:
            for k in new_weights:
                new_weights[k] /= total
        else:
            # fallback to config defaults
            pass
        self.weights = new_weights
        log.info(f"Loaded fusion weights from {p}: {self.weights}")
        return {lobe.value: w for lobe, w in self.weights.items()}

    def save_weights(self, path: str | Path | None = None) -> Path:
        """Save current weights to JSON. Returns path."""
        p = Path(path) if path else DEFAULT_WEIGHTS_PATH
        p.parent.mkdir(parents=True, exist_ok=True)
        out = {lobe.value: round(float(w), 6) for lobe, w in self.weights.items()}
        p.write_text(
            json.dumps({"weights": out, "note": "learned fusion weights"}, indent=2),
            encoding="utf-8",
        )
        log.info(f"Saved fusion weights to {p}")
        return p

    def calibrate_weights(
        self,
        labeled_reports: list[dict],
        lr: float = 0.5,
        iterations: int = 500,
        l2: float = 0.01,
        save_path: str | Path | None = None,
    ) -> dict[str, float]:
        """
        Logistic regression via gradient descent (numpy only) on
        5 lobe scores -> presence label.

        Each item in labeled_reports should be dict with lobe scores and label:
          {"streamer":0.9, "controller":0.8, "screen":0.7, "outcome":0.5, "visual":0.6, "label":1}
        or {"scores":{"streamer":...}, "label":1} or {"lobe_contributions":{...}, "label":1}
        Label is 0/1 or boolean. Also accepts "presence" key as label.

        Returns new weights dict (normalized).
        """
        if not labeled_reports:
            raise ValueError("labeled_reports is empty")

        lobe_keys = [lobe.value for lobe in self.LOBE_ORDER]

        rows: list[list[float]] = []
        labels: list[float] = []

        for item in labeled_reports:
            # extract label
            label = None
            for k in ("label", "presence", "y", "target"):
                if k in item:
                    label = item[k]
                    break
            if label is None:
                # maybe nested?
                continue
            label = 1.0 if bool(label) is True or float(label) > 0.5 else 0.0

            # extract scores
            scores: dict[str, float] = {}
            if "scores" in item and isinstance(item["scores"], dict):
                scores = item["scores"]
            elif "lobe_contributions" in item and isinstance(item["lobe_contributions"], dict):
                scores = item["lobe_contributions"]
            elif "features" in item and isinstance(item["features"], (list, tuple)):
                # assume ordered list
                feats = list(item["features"])
                scores = {
                    k: float(feats[i]) if i < len(feats) else 0.0 for i, k in enumerate(lobe_keys)
                }
            else:
                # flat dict with lobe keys
                scores = {k: float(item.get(k, 0.0)) for k in lobe_keys}

            row = [float(scores.get(k, 0.0)) for k in lobe_keys]
            rows.append(row)
            labels.append(label)

        if not rows:
            raise ValueError("No valid rows extracted from labeled_reports")

        X = np.array(rows, dtype=np.float64)  # N x 5
        y = np.array(labels, dtype=np.float64)  # N

        N, D = X.shape

        # init from current weights
        w = np.array([self.weights[lobe] for lobe in self.LOBE_ORDER], dtype=np.float64)
        # ensure positive start
        w = np.clip(w, 0.01, 1.0)
        b = 0.0

        # gradient descent
        for _it in range(iterations):
            logits = X @ w + b  # N
            # sigmoid
            probs = _sigmoid(logits)  # N
            # gradients
            err = probs - y  # N
            grad_w = (X.T @ err) / N + l2 * w
            grad_b = float(err.mean())
            w -= lr * grad_w
            b -= lr * grad_b
            # keep weights non-negative for interpretability
            w = np.maximum(w, 0.0)

        # normalize to sum 1 (if all zero, fallback)
        total = w.sum()
        if total > 1e-9:
            w /= total
        else:
            w = np.array([0.2] * D)

        # apply
        for i, lobe in enumerate(self.LOBE_ORDER):
            self.weights[lobe] = float(w[i])

        # save if requested or default path
        out_path = Path(save_path) if save_path else DEFAULT_WEIGHTS_PATH
        try:
            self.save_weights(out_path)
        except Exception as e:
            log.warning(f"Failed to save calibrated weights: {e}")

        result = {lobe.value: round(float(w[i]), 6) for i, lobe in enumerate(self.LOBE_ORDER)}
        result["_bias"] = round(float(b), 6)
        log.info(f"Calibrated weights: {result}")
        return {k: v for k, v in result.items() if not k.startswith("_")}

    # ── coupling stats ───────────────────────────────────────────────────────

    def get_coupling_stats(self) -> dict[str, float]:
        """Return current coupling analyzer stats (last window)."""
        with self._lock:
            # compute fresh coupling for reporting
            stats = self._coupling.compute_coupling(window_s=5.0)
            return dict(stats)

    # ── existing public API unchanged ───────────────────────────────────────

    def set_report_callback(self, callback: Callable[[PresenceReport], None]) -> None:
        """Set callback for when new report is generated."""
        self._report_callback = callback

    def start(self) -> None:
        """Start fusion engine (subscription is already active)."""
        pass

    def is_running(self) -> bool:
        """Fusion engine is running as long as it is subscribed to the bus."""
        return True

    # Lobe presence callbacks (called directly by lobe runtimes)
    def update_streamer_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            state = self._lobe_state[SourceLobe.STREAMER]
            state["presence_sync_ok"] = status.get("presence_sync_ok", False)
            state["activity_level"] = status.get("activity", "idle")
            state["motion"] = status.get("motion", 0.0)
            self._presence_sync_ok = status.get("presence_sync_ok", False)

    def update_controller_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            state = self._lobe_state[SourceLobe.CONTROLLER]
            state["causal_density"] = status.get("causal_density", 0)
            state["last_trigger"] = status.get("last_trigger", 0.0)

    def update_screen_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            state = self._lobe_state[SourceLobe.SCREEN]
            state["coupling_score"] = status.get("coupling_score", 0.0)

    def update_outcome_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            state = self._lobe_state[SourceLobe.OUTCOME]
            state["last_event"] = status.get("last_event")
            state["home_score"] = status.get("home_score", 0)
            state["away_score"] = status.get("away_score", 0)
            state["outcome_coherence"] = min(1.0, len(state.get("outcome_events", [])) * 0.1 + 0.1)

    def update_visual_status(self, status: dict[str, Any]) -> None:
        with self._lock:
            state = self._lobe_state[SourceLobe.VISUAL]
            state["game_state"] = status.get("game_state")
            state["confidence"] = status.get("confidence", 0.0)
            state["cross_modal_verdict"] = status.get("game_state")
            state["cross_modal_confidence"] = status.get("confidence", 0.0)

    def stop(self) -> None:
        """Stop fusion engine."""
        self._unsubscribe()

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT HANDLER
    # ──────────────────────────────────────────────────────────────────────────

    def _on_event(self, event) -> None:
        """Process incoming event from bus."""
        with self._lock:
            # Ignore our own presence_report emissions to prevent recursion
            if event.type == "presence_report":
                return

            lobe = event.source_lobe
            now_ns = event.clock_ns

            # Track event timing
            self._lobe_last_event_ns[lobe] = now_ns
            self._lobe_event_counts[lobe] += 1

            # Update per-lobe state based on event type
            self._update_lobe_state(lobe, event)

            # Check for anomalies
            self._check_anomalies(now_ns)

            # Emit updated report
            self._emit_report()

    def _update_lobe_state(self, lobe: SourceLobe, event) -> None:
        """Update lobe state from event."""
        state = self._lobe_state[lobe]
        payload = event.payload

        if lobe == SourceLobe.STREAMER:
            if event.type == EventType.ACTIVITY:
                state["activity_level"] = payload.get("level", "idle")
                state["motion"] = payload.get("motion", 0.0)
                state["presence_sync_ok"] = payload.get("presence_sync_ok", False)
                state["last_controller_s_ago"] = payload.get("last_controller_s_ago")
                self._presence_sync_ok = payload.get("presence_sync_ok", False)
                if payload.get("last_controller_s_ago") is not None:
                    self._last_controller_sync_ns = event.clock_ns - int(
                        payload["last_controller_s_ago"] * 1e9
                    )

            elif event.type == EventType.FRAME_STATS:
                state["fps"] = payload.get("fps_meas", 0.0)
                state["frames"] = payload.get("n", 0)
                state["presence_sync_ok"] = payload.get("presence_sync_ok", False)

            elif event.type == EventType.ZONE:
                zone_id = payload.get("zone_id")
                if zone_id:
                    state[f"zone_{zone_id}"] = {
                        "state": payload.get("state"),
                        "delta": payload.get("delta"),
                        "presence_sync_ok": payload.get("presence_sync_ok", False),
                    }

        elif lobe == SourceLobe.CONTROLLER:
            if event.type == EventType.TRIGGER_ONSET:
                state.setdefault("trigger_onsets", []).append(
                    {
                        "trigger": payload.get("trigger"),
                        "amplitude": payload.get("amplitude"),
                        "ts": event.clock_ns,
                    }
                )
                state["causal_density"] = len(state["trigger_onsets"])
                # feed coupling analyzer
                self._coupling.add_controller_event(event.clock_ns)
                # refresh coupling in screen state
                coupling = self._coupling.compute_coupling(window_s=5.0)
                screen_state = self._lobe_state[SourceLobe.SCREEN]
                screen_state["coupling_score"] = coupling["coupling_score"]
                screen_state["best_lag_ms"] = coupling["best_lag_ms"]
                screen_state["negative_control"] = coupling["negative_control"]
                screen_state["decoupled_energy"] = coupling["decoupled_energy"]

            elif event.type == EventType.STICK_MOTION:
                state.setdefault("stick_motions", []).append(
                    {
                        "stick": payload.get("stick"),
                        "x": payload.get("x"),
                        "y": payload.get("y"),
                        "ts": event.clock_ns,
                    }
                )

            elif event.type == EventType.TREMOR_SAMPLE:
                state.setdefault("tremor_samples", []).append(
                    {
                        "gyro": payload.get("gyro"),
                        "accel": payload.get("accel"),
                        "ts": event.clock_ns,
                    }
                )

            elif event.type == EventType.CONTROLLER_EVENT:
                if "causal_parent_ns" in payload:
                    state["last_causal_parent_ns"] = payload["causal_parent_ns"]

        elif lobe == SourceLobe.SCREEN:
            if event.type == EventType.COUPLING_SCORE:
                state["coupling_score"] = payload.get("coupling_score", 0.0)
                state["negative_control"] = payload.get("negative_control", 0.0)
                state["best_lag_ms"] = payload.get("best_lag_ms", 0.0)
                # also keep decoupled_energy if provided
                if "decoupled_energy" in payload:
                    state["decoupled_energy"] = payload.get("decoupled_energy", 0.0)

            elif event.type == EventType.CV_MOTION:
                motion_val = float(payload.get("motion", 0.0))
                state["cv_motion"] = motion_val
                # feed coupling analyzer
                self._coupling.add_motion_sample(event.clock_ns, motion_val)
                coupling = self._coupling.compute_coupling(window_s=5.0)
                state["coupling_score"] = coupling["coupling_score"]
                state["best_lag_ms"] = coupling["best_lag_ms"]
                state["negative_control"] = coupling["negative_control"]
                state["decoupled_energy"] = coupling["decoupled_energy"]

            elif event.type == EventType.OCR_HUD:
                state["ocr_hud"] = payload.get("text", "")

        elif lobe == SourceLobe.OUTCOME:
            if event.type == EventType.OUTCOME_EVENT:
                state.setdefault("outcome_events", []).append(
                    {
                        "event_name": payload.get("event_name"),
                        "confidence": payload.get("confidence"),
                        "fields": payload.get("fields", {}),
                        "ts": event.clock_ns,
                    }
                )
                state["outcome_coherence"] = min(1.0, len(state["outcome_events"]) * 0.1)

        elif lobe == SourceLobe.VISUAL:
            if event.type == EventType.VISUAL_CONTEXT:
                raw_category = payload.get("game_category")
                raw_state = payload.get("game_state")
                conf = payload.get("confidence", 0.0)
                cat, st, conf = self._visual_hysteresis.update(raw_category, raw_state, conf)
                state["game_category"] = cat
                state["game_state"] = st
                state["confidence"] = conf
                # Expose smoothed verdict to the legacy score path
                state["cross_modal_verdict"] = st
                state["cross_modal_confidence"] = conf

            elif event.type == EventType.CROSS_MODAL_VERDICT:
                state["cross_modal_verdict"] = payload.get("verdict")
                state["cross_modal_confidence"] = payload.get("confidence", 0.0)

    # ──────────────────────────────────────────────────────────────────────────
    # ANOMALY DETECTION  (kept compatible)
    # ──────────────────────────────────────────────────────────────────────────

    def _check_anomalies(self, now_ns: int) -> None:
        """Detect cross-lobe anomalies, dropping any that are no longer active."""
        active: list[Anomaly] = []

        # 1. Temporal desync - lobes not emitting recently
        for lobe, weight in self.weights.items():
            if weight > 0 and lobe in self._lobe_last_event_ns:
                age_ns = now_ns - self._lobe_last_event_ns[lobe]
                if age_ns > 5_000_000_000:  # 5 seconds
                    active.append(
                        Anomaly(
                            type="temporal_desync",
                            severity="medium" if age_ns < 30_000_000_000 else "high",
                            description=f"Lobe {lobe.value} silent for {age_ns / 1e9:.1f}s",
                            lobes_involved=[lobe],
                            timestamp_ns=now_ns,
                            details={"age_ns": age_ns, "weight": weight},
                        )
                    )

        # 2. Presence sync mismatch - streamer says synced but controller stale
        if (
            SourceLobe.STREAMER in self._lobe_state
            and SourceLobe.CONTROLLER in self._lobe_last_event_ns
        ):
            streamer_state = self._lobe_state[SourceLobe.STREAMER]
            if streamer_state.get("presence_sync_ok") is True:
                last_ctrl = self._lobe_last_event_ns[SourceLobe.CONTROLLER]
                age_ns = now_ns - last_ctrl
                if age_ns > 10_000_000_000:  # 10 seconds
                    active.append(
                        Anomaly(
                            type="contradiction",
                            severity="high",
                            description="Streamer reports presence_sync but controller inactive >10s",
                            lobes_involved=[SourceLobe.STREAMER, SourceLobe.CONTROLLER],
                            timestamp_ns=now_ns,
                            details={"controller_age_ns": age_ns},
                        )
                    )

        # 3. Missing enabled lobes
        if self.config.streamer.enabled and SourceLobe.STREAMER not in self._lobe_last_event_ns:
            active.append(
                Anomaly(
                    type="missing_lobe",
                    severity="high",
                    description="Streamer lobe enabled but no events received",
                    lobes_involved=[SourceLobe.STREAMER],
                    timestamp_ns=now_ns,
                )
            )

        if self.config.controller.enabled and SourceLobe.CONTROLLER not in self._lobe_last_event_ns:
            active.append(
                Anomaly(
                    type="missing_lobe",
                    severity="high",
                    description="Controller lobe enabled but no events received",
                    lobes_involved=[SourceLobe.CONTROLLER],
                    timestamp_ns=now_ns,
                )
            )

        # 4. Outcome without controller (for games requiring input)
        if (
            self.config.outcome.enabled
            and self.config.controller.enabled
            and SourceLobe.OUTCOME in self._lobe_state
            and SourceLobe.CONTROLLER in self._lobe_last_event_ns
        ):
            outcome_state = self._lobe_state[SourceLobe.OUTCOME]
            last_ctrl = self._lobe_last_event_ns[SourceLobe.CONTROLLER]
            if outcome_state.get("outcome_events") and (now_ns - last_ctrl) > 5_000_000_000:
                active.append(
                    Anomaly(
                        type="spatial_mismatch",
                        severity="medium",
                        description="Outcome events detected but no recent controller input",
                        lobes_involved=[SourceLobe.OUTCOME, SourceLobe.CONTROLLER],
                        timestamp_ns=now_ns,
                    )
                )

        # Replace persistent list with currently active anomalies
        old_anomalies = self._anomalies
        self._anomalies = active

        # Trim if too many
        if len(self._anomalies) > self._max_anomalies:
            self._anomalies = self._anomalies[-self._max_anomalies :]

        # Log only newly active anomalies
        for anomaly in self._anomalies:
            if not self._anomaly_exists(anomaly, old_anomalies):
                log.warning(f"Anomaly detected: {anomaly.type} - {anomaly.description}")

    def _anomaly_exists(self, new_anomaly: Anomaly, anomalies: list[Anomaly] | None = None) -> bool:
        """Check if a similar anomaly is already in the provided list (default: current list)."""
        for existing in anomalies if anomalies is not None else self._anomalies:
            if (
                existing.type == new_anomaly.type
                and existing.lobes_involved == new_anomaly.lobes_involved
                and new_anomaly.timestamp_ns - existing.timestamp_ns < 10_000_000_000
            ):
                return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # REPORT GENERATION
    # ──────────────────────────────────────────────────────────────────────────

    def _compute_lobe_scores(self) -> dict[SourceLobe, LobeContribution]:
        """Compute score for each lobe. Kept compatible with original logic."""
        contributions = {}

        for lobe, weight in self.weights.items():
            if weight == 0:
                contributions[lobe] = LobeContribution(
                    lobe=lobe, weight=weight, score=0.0, confidence=0.0, last_event_ns=0, details={}
                )
                continue

            state = self._lobe_state.get(lobe, {})
            last_ns = self._lobe_last_event_ns.get(lobe, 0)

            if lobe == SourceLobe.STREAMER:
                presence = state.get("presence_sync_ok", False)
                activity = state.get("activity_level", "idle")
                score = 1.0 if presence else (0.5 if activity in ("low", "high") else 0.0)
                confidence = 0.9 if presence else 0.5

            elif lobe == SourceLobe.CONTROLLER:
                causal = state.get("causal_density", 0)
                tremor_count = len(state.get("tremor_samples", []))
                stick_count = len(state.get("stick_motions", []))
                score = min(1.0, (causal * 0.2) + (tremor_count * 0.01) + (stick_count * 0.01))
                confidence = min(1.0, (causal + tremor_count + stick_count) * 0.05)

            elif lobe == SourceLobe.SCREEN:
                coupling = state.get("coupling_score", 0.0)
                score = max(0.0, min(1.0, coupling))
                confidence = 0.7 if coupling > 0.5 else 0.3

            elif lobe == SourceLobe.OUTCOME:
                coherence = state.get("outcome_coherence", 0.0)
                score = coherence
                confidence = 0.8 if coherence > 0.5 else 0.4

            elif lobe == SourceLobe.VISUAL:
                # Prefer smoothed game_category; fall back to legacy cross_modal_verdict
                verdict = state.get("game_category") or state.get("cross_modal_verdict")
                v_conf = state.get("confidence", state.get("cross_modal_confidence", 0.0))
                # Treat only active gameplay categories / confirmed verdicts as present
                non_present = {"unknown", "menu", "inconclusive"}
                score = v_conf if verdict and str(verdict).lower() not in non_present else 0.0
                confidence = v_conf

            else:
                score = 0.0
                confidence = 0.0

            contributions[lobe] = LobeContribution(
                lobe=lobe,
                weight=weight,
                score=score,
                confidence=confidence,
                last_event_ns=last_ns,
                details=state,
            )

        return contributions

    def _compute_weighted_verdict(
        self, contributions: dict[SourceLobe, LobeContribution]
    ) -> tuple[str, float]:
        """Compute weighted verdict from lobe contributions with sigmoid calibration."""
        total_weight = 0.0
        weighted_sum = 0.0

        for contrib in contributions.values():
            if contrib.weight > 0:
                total_weight += contrib.weight
                weighted_sum += contrib.score * contrib.weight

        if total_weight == 0:
            return "uncertain", 0.0

        final_score = weighted_sum / total_weight  # 0..1

        # confidence calibration: sigmoid(weighted_sum - 0.5) per spec
        # spec formula is literal; gives ~0.377..0.622 range which is narrow
        # but compliant. Use literal.
        calibrated = float(_sigmoid(final_score - 0.5))

        # Map score to verdict (unchanged thresholds)
        if final_score >= 0.8:
            verdict = "present"
        elif final_score >= 0.5:
            verdict = "likely_present"
        elif final_score >= 0.2:
            verdict = "uncertain"
        else:
            verdict = "absent"

        return verdict, calibrated

    def _emit_report(self, force: bool = False) -> None:
        """Generate and emit presence report."""
        with self._lock:
            now_ns = clock_ns()
            contributions = self._compute_lobe_scores()
            verdict, confidence = self._compute_weighted_verdict(contributions)

            presence_sync = self._presence_sync_ok
            lobe_contribs = {lobe.value: round(c.score, 3) for lobe, c in contributions.items()}

            # coupling fields for details
            coupling_stats = self._coupling.get_stats()

            report = PresenceReport(
                session_id=self.session_id,
                clock_ns=now_ns,
                session_head_ns=self.session_head_ns,
                presence_sync_ok=presence_sync,
                weighted_verdict=verdict,
                lobe_contributions=lobe_contribs,
                anomalies=list(self._anomalies),
                confidence=round(confidence, 3),
                fusion_weights={lobe.value: weight for lobe, weight in self.weights.items()},
                details={
                    "lobe_event_counts": dict(self._lobe_event_counts),
                    "anomaly_count": len(self._anomalies),
                    # coupling fields
                    "coupling_score": coupling_stats.get("coupling_score", 0.0),
                    "best_lag_ms": coupling_stats.get("best_lag_ms", 0.0),
                    "negative_control": coupling_stats.get("negative_control", 0.0),
                    "decoupled_energy": coupling_stats.get("decoupled_energy", 1.0),
                    "coupling": coupling_stats,
                },
            )

            # Emit to bus
            self.bus.emit_raw(
                source_lobe=SourceLobe.STREAMER,
                event_type="presence_report",
                payload=report.to_dict(),
                clock_ns_override=now_ns,
                session_head_ns=self.session_head_ns,
            )

            if self._report_callback:
                try:
                    self._report_callback(report)
                except Exception as e:
                    log.error(f"Report callback error: {e}")

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC QUERY METHODS
    # ──────────────────────────────────────────────────────────────────────────

    def get_current_report(self) -> PresenceReport:
        """Get current presence report (generates fresh)."""
        with self._lock:
            now_ns = clock_ns()
            contributions = self._compute_lobe_scores()
            verdict, confidence = self._compute_weighted_verdict(contributions)
            coupling_stats = self._coupling.get_stats()

            return PresenceReport(
                session_id=self.session_id,
                clock_ns=now_ns,
                session_head_ns=self.session_head_ns,
                presence_sync_ok=self._presence_sync_ok,
                weighted_verdict=verdict,
                lobe_contributions={
                    lobe.value: round(c.score, 3) for lobe, c in contributions.items()
                },
                anomalies=list(self._anomalies),
                confidence=round(confidence, 3),
                fusion_weights={lobe.value: weight for lobe, weight in self.weights.items()},
                details={
                    "lobe_event_counts": dict(self._lobe_event_counts),
                    "anomaly_count": len(self._anomalies),
                    "coupling_score": coupling_stats.get("coupling_score", 0.0),
                    "best_lag_ms": coupling_stats.get("best_lag_ms", 0.0),
                    "negative_control": coupling_stats.get("negative_control", 0.0),
                    "decoupled_energy": coupling_stats.get("decoupled_energy", 1.0),
                    "coupling": coupling_stats,
                },
            )

    def get_anomalies(self) -> list[Anomaly]:
        """Get current anomalies."""
        with self._lock:
            return list(self._anomalies)

    def get_lobe_stats(self) -> dict[str, Any]:
        """Get per-lobe statistics."""
        with self._lock:
            return {
                "event_counts": dict(self._lobe_event_counts),
                "last_event_age_ns": {
                    lobe.value: clock_ns() - ns for lobe, ns in self._lobe_last_event_ns.items()
                },
                "weights": {lobe.value: weight for lobe, weight in self.weights.items()},
            }


# ──────────────────────────────────────────────────────────────────────────────
# CONVENIENCE FUNCTION
# ──────────────────────────────────────────────────────────────────────────────


def create_fusion_engine(
    config: RetinaUnifiedConfig,
    bus: RetinaEventBus,
) -> PresenceFusionEngine:
    """Create and start fusion engine."""
    return PresenceFusionEngine(config, bus)
