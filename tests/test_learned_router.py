"""Tests for the learned router (Trio P2 advanced)."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from qoresence.a2a.learned_router import (
    MIN_SAMPLES_FOR_LEARNED,
    FeatureExtractor,
    FeedbackEntry,
    FeedbackStore,
    LearnedRouter,
    LearnedRouterDecision,
    UtilityModel,
)

# ── FeatureExtractor ─────────────────────────────────────────────────────────


def test_extract_features_football():
    """Should extract 10 features for a football situation."""
    sit = {
        "game_category": "football",
        "game_state": "gameplay",
        "visual_confidence": 0.9,
        "coupling": 0.5,
        "drive_phase": "pressure",
        "last_outcome_event": "touchdown",
    }
    features = FeatureExtractor.extract(sit)
    assert len(features) == 10
    assert features[0] == 0.9  # visual_confidence
    assert features[1] == 0.5  # coupling
    assert features[2] == 1.0  # is_pressure
    assert features[4] == 1.0  # is_big_play
    assert features[7] == 1.0  # is_gameplay
    assert features[8] == 1.0  # is_football


def test_extract_features_shooter():
    """Should extract features for a shooter situation."""
    sit = {
        "game_category": "shooter",
        "game_state": "gameplay",
        "visual_confidence": 0.8,
        "coupling": 0.6,
    }
    features = FeatureExtractor.extract(sit)
    assert features[8] == 0.0  # not football
    assert features[9] == 1.0  # is_shooter


def test_extract_features_empty_situation():
    """Should handle empty situation gracefully."""
    features = FeatureExtractor.extract({})
    assert len(features) == 10
    assert all(0.0 <= f <= 1.0 for f in features)


def test_extract_features_with_history():
    """Should use evidence history for recency features."""
    now = time.time()
    history = [
        {"ts_ns": int(now * 1e9), "trigger_reason": "touchdown"},
        {"ts_ns": int((now - 30) * 1e9), "trigger_reason": "score_changed"},
    ]
    sit = {"game_state": "gameplay"}
    features = FeatureExtractor.extract(sit, history)
    # seconds_since_last should be small (recent)
    assert features[5] < 0.1
    # events_60s should be 2 (both within 60s)
    assert features[6] == 0.2  # 2/10 normalized


# ── UtilityModel ─────────────────────────────────────────────────────────────


def test_utility_model_score():
    """Should return utility and confidence."""
    model = UtilityModel()
    features = [0.9, 0.5, 1.0, 0.0, 1.0, 0.1, 0.1, 1.0, 1.0, 0.0]
    utility, confidence = model.score(features)
    assert 0.0 <= utility <= 1.0
    assert confidence == 0.0  # not trained yet


def test_utility_model_train():
    """Should train and increase confidence."""
    model = UtilityModel()
    features_list = [
        [0.9, 0.5, 1.0, 0.0, 1.0, 0.1, 0.1, 1.0, 1.0, 0.0],
        [0.1, 0.1, 0.0, 0.0, 0.0, 0.9, 0.0, 1.0, 1.0, 0.0],
    ]
    labels = [1, -1]  # good fire, bad fire
    loss = model.train(features_list, labels, epochs=10)
    assert loss >= 0.0
    assert model.trained is True
    assert model.n_samples == 2

    # Score should reflect training
    utility_good, conf = model.score(features_list[0])
    utility_bad, _ = model.score(features_list[1])
    assert conf > 0.0
    # Good fire should have higher utility than bad fire
    assert utility_good > utility_bad


def test_utility_model_save_load():
    """Should serialize and deserialize."""
    model = UtilityModel()
    model.train([[0.5] * 10, [0.1] * 10], [1, -1], epochs=5)
    data = model.to_dict()
    model2 = UtilityModel()
    model2.from_dict(data)
    assert model2.weights == model.weights
    assert model2.bias == model.bias
    assert model2.trained is True


# ── FeedbackStore ────────────────────────────────────────────────────────────


def test_feedback_store_add_and_count(tmp_path):
    """Should store feedback entries."""
    store = FeedbackStore(path=tmp_path / "feedback.jsonl")
    store.add(FeedbackEntry(evidence_clock_ns=123, rating=1, timestamp=time.time()))
    store.add(FeedbackEntry(evidence_clock_ns=456, rating=-1, timestamp=time.time()))
    assert store.count == 2


def test_feedback_store_persists(tmp_path):
    """Should persist feedback to disk."""
    path = tmp_path / "feedback.jsonl"
    store = FeedbackStore(path=path)
    store.add(FeedbackEntry(evidence_clock_ns=123, rating=1))
    assert path.exists()

    # Reload
    store2 = FeedbackStore(path=path)
    assert store2.count == 1


def test_feedback_store_ratings_by_clock_ns(tmp_path):
    """Should map clock_ns to ratings."""
    store = FeedbackStore(path=tmp_path / "fb.jsonl")
    store.add(FeedbackEntry(evidence_clock_ns=100, rating=1))
    store.add(FeedbackEntry(evidence_clock_ns=200, rating=-1))
    ratings = store.ratings_by_clock_ns()
    assert ratings[100] == 1
    assert ratings[200] == -1


def test_feedback_store_clear(tmp_path):
    """Should clear all entries."""
    path = tmp_path / "fb.jsonl"
    store = FeedbackStore(path=path)
    store.add(FeedbackEntry(evidence_clock_ns=1, rating=1))
    store.clear()
    assert store.count == 0
    assert not path.exists()


# ── LearnedRouter ────────────────────────────────────────────────────────────


def test_learned_router_must_fire_overrides():
    """Must-fire predicates should always override the learned model."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        sit = {"game_category": "football", "last_outcome_event": "touchdown"}
        decision = router.evaluate(sit)
        assert decision.fired is True
        assert decision.must_fire_hit == "big_play"
        assert decision.source == "rule"


def test_learned_router_falls_back_without_data():
    """Should fall back to rule-based without training data."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        sit = {"game_category": "football", "game_state": "gameplay"}
        decision = router.evaluate(sit)
        assert decision.fired is False
        assert decision.source == "rule"


def test_learned_router_uses_model_when_trained():
    """Should use the learned model when enough data is available."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        # Manually train the model with enough samples
        features_list = [
            [0.9, 0.5, 1.0, 0.0, 1.0, 0.1, 0.1, 1.0, 1.0, 0.0]
        ] * MIN_SAMPLES_FOR_LEARNED
        labels = [1] * MIN_SAMPLES_FOR_LEARNED
        router.model.train(features_list, labels, epochs=10)

        # Now evaluate — should use learned model
        sit = {"game_category": "football", "game_state": "gameplay", "visual_confidence": 0.9}
        decision = router.evaluate(sit)
        assert decision.source == "learned"
        assert decision.utility_score > 0.0


def test_learned_router_record_feedback():
    """Should record and persist feedback."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        router.record_feedback(evidence_clock_ns=123, rating=1)
        router.record_feedback(evidence_clock_ns=456, rating=-1)
        assert router.feedback_count == 2


def test_learned_router_train_from_feedback():
    """Should train the model from feedback data."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        # Record feedback
        router.record_feedback(evidence_clock_ns=100, rating=1)
        router.record_feedback(evidence_clock_ns=200, rating=-1)

        # Create matching evidence chains
        evidence_chains = [
            {
                "clock_ns": 100,
                "confidence": 0.9,
                "coupling_score": 0.5,
                "drive_phase": "pressure",
                "cited_events": [{"event_name": "touchdown"}],
            },
            {
                "clock_ns": 200,
                "confidence": 0.1,
                "coupling_score": 0.1,
                "drive_phase": "open",
                "cited_events": [{"event_name": "first_down"}],
            },
        ]

        loss = router.train_from_feedback(evidence_chains)
        assert loss >= 0.0
        assert router.model.trained is True
        assert router.model.n_samples == 2

        # Model should be saved
        assert (Path(td) / "model.json").exists()


def test_learned_router_train_no_feedback():
    """Should handle training with no feedback gracefully."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        loss = router.train_from_feedback([])
        assert loss == 0.0
        assert router.model.trained is False


def test_learned_router_stats():
    """Should return stats dictionary."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        stats = router.stats()
        assert "feedback_count" in stats
        assert "model_samples" in stats
        assert "is_learned" in stats
        assert "weights" in stats


def test_learned_router_is_learned_property():
    """is_learned should be False until enough data is trained."""
    with tempfile.TemporaryDirectory() as td:
        router = LearnedRouter(
            feedback_path=Path(td) / "fb.jsonl",
            model_path=Path(td) / "model.json",
        )
        assert router.is_learned is False

        # Train with enough samples
        features = [[0.5] * 10] * MIN_SAMPLES_FOR_LEARNED
        labels = [1] * MIN_SAMPLES_FOR_LEARNED
        router.model.train(features, labels, epochs=1)
        assert router.is_learned is True


def test_learned_router_decision_to_dict():
    """LearnedRouterDecision should serialize to dict."""
    d = LearnedRouterDecision(
        fired=True,
        reason="touchdown",
        must_fire_hit="big_play",
        utility_score=0.85,
        confidence=0.7,
        source="rule",
    )
    dd = d.to_dict()
    assert dd["fired"] is True
    assert dd["utility_score"] == 0.85
    assert dd["source"] == "rule"
