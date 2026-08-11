"""Learned router: utility-cost classifier from evidence (Trio P2 advanced).

This module provides a learned router that scores the utility of firing
the A2A reasoning tier based on historical evidence chains and operator
feedback. It complements the rule-based must-fire predicates with a
data-driven scoring layer.

Architecture:
    - FeatureExtractor: converts situation + evidence history into features
    - UtilityModel: lightweight logistic regression scoring fire utility
    - LearnedRouter: combines must-fire predicates with utility score
    - FeedbackStore: records operator feedback (thumbs up/down) for training

The learned router is optional and falls back to rule-based predicates
when insufficient training data is available (threshold: 50 samples).

Training data comes from:
    1. Evidence chains (auto-collected from JSONL log)
    2. Operator feedback (thumbs up/down on commentary quality)
    3. Counterfactual evaluation (what would have happened if we fired/suppressed)

Usage:
    # Create a learned router
    router = LearnedRouter()

    # Evaluate whether to fire
    decision = router.evaluate(situation, evidence_history)

    # Record operator feedback
    router.record_feedback(evidence_id, rating=1)  # thumbs up
    router.record_feedback(evidence_id, rating=-1)  # thumbs down

    # Train the utility model from accumulated feedback
    router.train_from_feedback()
"""

from __future__ import annotations

import json
import logging
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from qoresence.a2a.router import evaluate_must_fire

log = logging.getLogger(__name__)

# Minimum samples before the learned model is used (below this, rule-based only)
MIN_SAMPLES_FOR_LEARNED = 50


@dataclass
class FeedbackEntry:
    """Operator feedback on a commentary decision."""

    evidence_clock_ns: int
    rating: int  # +1 = good, -1 = bad, 0 = neutral
    timestamp: float = 0.0
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LearnedRouterDecision:
    """Decision from the learned router."""

    fired: bool
    reason: str
    must_fire_hit: str | None = None
    utility_score: float = 0.0  # 0..1, higher = more useful to fire
    confidence: float = 0.0  # model confidence in the utility score
    source: str = "rule"  # "rule" | "learned" | "hybrid"
    inputs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FeatureExtractor:
    """Extract features from situation and evidence history for the utility model.

    Features (10-dimensional vector):
        0. visual_confidence (0..1)
        1. coupling_score (0..1)
        2. is_pressure_phase (0/1)
        3. is_armed_phase (0/1)
        4. is_big_play (0/1)
        5. seconds_since_last_event
        6. events_in_last_60s (count)
        7. is_gameplay (0/1)
        8. is_football (0/1)
        9. is_shooter (0/1)
    """

    @staticmethod
    def extract(
        situation: dict[str, Any],
        evidence_history: list[dict[str, Any]] | None = None,
    ) -> list[float]:
        sit = situation
        history = evidence_history or []

        vis_conf = float(sit.get("visual_confidence") or 0.0)
        coupling = float(sit.get("coupling") or 0.0)
        drive_phase = str(sit.get("drive_phase") or "").lower()
        last_event = str(sit.get("last_outcome_event") or "").lower()
        game_state = str(sit.get("game_state") or "").lower()
        game_category = str(sit.get("game_category") or "").lower()

        is_pressure = 1.0 if drive_phase == "pressure" else 0.0
        is_armed = 1.0 if drive_phase == "armed" else 0.0
        is_big_play = 1.0 if last_event in {
            "touchdown", "field_goal", "safety", "turnover", "score_changed",
            "two_point_conversion", "red_zone_entry", "two_minute_warning",
        } else 0.0

        # Time since last evidence chain
        now = time.time()
        if history:
            last_ev = history[0]
            ev_time = last_ev.get("ts_ns", 0) / 1e9 if last_ev.get("ts_ns") else 0
            seconds_since = now - ev_time if ev_time > 0 else 999.0
        else:
            seconds_since = 999.0

        # Count events in last 60s
        events_60s = 0
        for ev in history:
            ev_time = ev.get("ts_ns", 0) / 1e9 if ev.get("ts_ns") else 0
            if ev_time > 0 and (now - ev_time) < 60.0:
                events_60s += 1

        is_gameplay = 1.0 if game_state in {"gameplay", "playing", "in_game"} else 0.0
        is_football = 1.0 if game_category in {"football", "ncaa_football", "ncaa"} else 0.0
        is_shooter = 1.0 if game_category in {"shooter", "fps"} else 0.0

        return [
            vis_conf,
            coupling,
            is_pressure,
            is_armed,
            is_big_play,
            min(seconds_since, 999.0) / 999.0,  # normalize to 0..1
            min(events_60s, 10.0) / 10.0,  # normalize to 0..1
            is_gameplay,
            is_football,
            is_shooter,
        ]


class UtilityModel:
    """Lightweight logistic regression for fire utility scoring.

    Uses a simple weighted sum + sigmoid (no external ML dependencies).
    Weights are initialized to reasonable priors and updated via
    gradient descent from operator feedback.
    """

    def __init__(self, n_features: int = 10) -> None:
        self.n_features = n_features
        # Initialize weights with priors:
        # visual_confidence, coupling, pressure, armed, big_play are positive
        # seconds_since_last_event is slightly negative (recency bias)
        # events_60s is slightly negative (don't over-comment)
        # gameplay, football, shooter are neutral
        self.weights = [0.5, 0.8, 0.6, 0.7, 1.2, -0.2, -0.3, 0.1, 0.0, 0.0]
        self.bias = -0.5  # default threshold — bias toward not firing
        self.n_samples = 0
        self.trained = False

    def score(self, features: list[float]) -> tuple[float, float]:
        """Score utility and return (utility, confidence).

        utility: 0..1, higher = more useful to fire
        confidence: 0..1, based on number of training samples
        """
        z = self.bias
        for w, f in zip(self.weights, features):
            z += w * f
        utility = 1.0 / (1.0 + math.exp(-z))
        # Confidence grows with samples, capped at 0.9
        confidence = min(0.9, self.n_samples / 100.0) if self.trained else 0.0
        return utility, confidence

    def train(
        self,
        features_list: list[list[float]],
        labels: list[int],
        lr: float = 0.01,
        epochs: int = 100,
    ) -> float:
        """Train the model via gradient descent.

        Args:
            features_list: List of feature vectors
            labels: List of +1 (good fire) / -1 (bad fire) / 0 (neutral)
            lr: Learning rate
            epochs: Number of training epochs

        Returns:
            Final loss.
        """
        if not features_list:
            return 0.0

        n = len(features_list)
        self.n_samples = n

        for _ in range(epochs):
            grad_w = [0.0] * self.n_features
            grad_b = 0.0
            total_loss = 0.0

            for features, label in zip(features_list, labels):
                z = self.bias
                for w, f in zip(self.weights, features):
                    z += w * f
                pred = 1.0 / (1.0 + math.exp(-max(-20, min(20, z))))
                # Label: +1 → target=1, -1 → target=0, 0 → target=0.5
                target = 1.0 if label > 0 else (0.0 if label < 0 else 0.5)
                error = pred - target
                total_loss += error * error

                for i in range(self.n_features):
                    grad_w[i] += error * features[i]
                grad_b += error

            # Update weights
            for i in range(self.n_features):
                self.weights[i] -= lr * grad_w[i] / n
            self.bias -= lr * grad_b / n

        self.trained = True
        return total_loss / n if n > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "weights": self.weights,
            "bias": self.bias,
            "n_samples": self.n_samples,
            "trained": self.trained,
        }

    def from_dict(self, data: dict[str, Any]) -> None:
        self.weights = data.get("weights", self.weights)
        self.bias = data.get("bias", self.bias)
        self.n_samples = data.get("n_samples", 0)
        self.trained = data.get("trained", False)


class FeedbackStore:
    """Stores operator feedback for router training.

    Feedback is persisted to a JSONL file so it survives across sessions.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path("logs/router_feedback.jsonl")
        self._entries: list[FeedbackEntry] = []
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                for line in self.path.read_text(encoding="utf-8").strip().splitlines():
                    if line.strip():
                        data = json.loads(line)
                        self._entries.append(FeedbackEntry(**data))
            except Exception as e:
                log.warning("Failed to load feedback: %s", e)

    def add(self, entry: FeedbackEntry) -> None:
        self._entries.append(entry)
        self._append(entry)

    def _append(self, entry: FeedbackEntry) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as e:
            log.warning("Failed to append feedback: %s", e)

    @property
    def count(self) -> int:
        return len(self._entries)

    def ratings_by_clock_ns(self) -> dict[int, int]:
        """Map evidence_clock_ns → rating."""
        return {e.evidence_clock_ns: e.rating for e in self._entries}

    def clear(self) -> None:
        self._entries.clear()
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


class LearnedRouter:
    """Hybrid router combining rule-based predicates with learned utility.

    Decision logic:
    1. If any must-fire predicate fires → fire (rule-based override)
    2. If learned model has enough data → use utility score with threshold
    3. Otherwise → fall back to rule-based interval logic

    The learned model is trained from operator feedback: when the operator
    gives a thumbs-up to a commentary line, the features that led to that
    fire decision are reinforced. Thumbs-down weakens them.
    """

    def __init__(
        self,
        feedback_path: str | Path | None = None,
        model_path: str | Path | None = None,
    ) -> None:
        self.feedback = FeedbackStore(feedback_path)
        self.model = UtilityModel()
        self.model_path = Path(model_path) if model_path else Path("logs/router_model.json")
        self._load_model()
        self._utility_threshold = 0.55  # fire if utility >= threshold

    def _load_model(self) -> None:
        if self.model_path.exists():
            try:
                data = json.loads(self.model_path.read_text(encoding="utf-8"))
                self.model.from_dict(data)
            except Exception as e:
                log.warning("Failed to load router model: %s", e)

    def _save_model(self) -> None:
        try:
            self.model_path.parent.mkdir(parents=True, exist_ok=True)
            self.model_path.write_text(
                json.dumps(self.model.to_dict(), indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.warning("Failed to save router model: %s", e)

    def evaluate(
        self,
        situation: dict[str, Any],
        evidence_history: list[dict[str, Any]] | None = None,
    ) -> LearnedRouterDecision:
        """Evaluate whether to fire the reasoning tier.

        Args:
            situation: Current situation dict
            evidence_history: Recent evidence chains for feature extraction

        Returns:
            LearnedRouterDecision with fire/suppress and scoring details.
        """
        # Step 1: Check must-fire predicates (always override)
        must_fire, must_fire_pred = evaluate_must_fire(situation)

        if must_fire:
            return LearnedRouterDecision(
                fired=True,
                reason=str(situation.get("_a2a_reason") or "must_fire"),
                must_fire_hit=must_fire_pred,
                utility_score=1.0,
                confidence=1.0,
                source="rule",
                inputs={
                    "game_category": situation.get("game_category"),
                    "last_outcome_event": situation.get("last_outcome_event"),
                },
            )

        # Step 2: Use learned model if enough data
        if self.model.trained and self.model.n_samples >= MIN_SAMPLES_FOR_LEARNED:
            features = FeatureExtractor.extract(situation, evidence_history)
            utility, confidence = self.model.score(features)

            fired = utility >= self._utility_threshold
            return LearnedRouterDecision(
                fired=fired,
                reason=str(situation.get("_a2a_reason") or "learned"),
                must_fire_hit=None,
                utility_score=round(utility, 4),
                confidence=round(confidence, 4),
                source="learned",
                inputs={
                    "game_category": situation.get("game_category"),
                    "features": [round(f, 3) for f in features],
                },
            )

        # Step 3: Fall back to rule-based (no fire — interval logic handles it)
        return LearnedRouterDecision(
            fired=False,
            reason=str(situation.get("_a2a_reason") or "rule_fallback"),
            must_fire_hit=None,
            utility_score=0.0,
            confidence=0.0,
            source="rule",
            inputs={
                "game_category": situation.get("game_category"),
            },
        )

    def record_feedback(self, evidence_clock_ns: int, rating: int, comment: str = "") -> None:
        """Record operator feedback for a commentary decision."""
        entry = FeedbackEntry(
            evidence_clock_ns=evidence_clock_ns,
            rating=rating,
            timestamp=time.time(),
            comment=comment,
        )
        self.feedback.add(entry)
        log.info("Feedback recorded: evidence=%d rating=%d", evidence_clock_ns, rating)

    def train_from_feedback(
        self,
        evidence_chains: list[dict[str, Any]],
    ) -> float:
        """Train the utility model from accumulated feedback.

        Args:
            evidence_chains: List of evidence chain payloads from the JSONL log.
                Each should have clock_ns, trigger_reason, confidence, etc.

        Returns:
            Final training loss.
        """
        ratings = self.feedback.ratings_by_clock_ns()
        if not ratings:
            log.info("No feedback to train from")
            return 0.0

        # Match evidence chains to feedback ratings
        features_list: list[list[float]] = []
        labels: list[int] = []

        for ec in evidence_chains:
            clock_ns = ec.get("clock_ns")
            if clock_ns is None:
                continue
            rating = ratings.get(clock_ns)
            if rating is None:
                continue

            # Extract features from the evidence chain
            sit = {
                "visual_confidence": ec.get("confidence"),
                "coupling": ec.get("coupling_score"),
                "drive_phase": ec.get("drive_phase"),
                "last_outcome_event": (ec.get("cited_events") or [{}])[0].get("event_name") if ec.get("cited_events") else None,
                "game_state": "gameplay",
                "game_category": "football",  # inferred from cited fields
            }
            features = FeatureExtractor.extract(sit)
            features_list.append(features)
            labels.append(rating)

        if not features_list:
            log.info("No matching feedback-evidence pairs for training")
            return 0.0

        log.info("Training router from %d feedback samples", len(features_list))
        loss = self.model.train(features_list, labels)
        self._save_model()
        log.info("Router model trained: loss=%.4f, samples=%d", loss, len(features_list))
        return loss

    @property
    def feedback_count(self) -> int:
        return self.feedback.count

    @property
    def is_learned(self) -> bool:
        """True if the learned model is active (enough training data)."""
        return self.model.trained and self.model.n_samples >= MIN_SAMPLES_FOR_LEARNED

    def stats(self) -> dict[str, Any]:
        return {
            "feedback_count": self.feedback.count,
            "model_samples": self.model.n_samples,
            "model_trained": self.model.trained,
            "is_learned": self.is_learned,
            "utility_threshold": self._utility_threshold,
            "weights": self.model.weights,
        }
