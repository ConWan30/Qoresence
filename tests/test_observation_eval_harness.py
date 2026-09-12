"""Observation eval harness — CI hard-fail on false confirmed claims."""

from pathlib import Path

import pytest

from qoresence.evals.observation import run_fixture
from qoresence.evals.observation.runner import discover_fixtures, run_all

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "qoresence" / "evals" / "observation" / "fixtures"


@pytest.fixture(scope="module")
def fixture_paths():
    paths = discover_fixtures(FIXTURE_DIR)
    assert paths, "observation eval fixtures missing"
    return paths


def test_eval_fixtures_zero_false_confirmed_claims(fixture_paths):
    for path in fixture_paths:
        metrics = run_fixture(path)
        assert metrics.false_confirmed_claims == 0, (
            f"{path.name}: false confirmed claims={metrics.false_confirmed_claims}"
        )


def test_eval_replay_consistency(fixture_paths):
    for path in fixture_paths:
        metrics = run_fixture(path)
        assert metrics.replay_consistent, f"{path.name}: replay mismatch"


def test_eval_abstention_reported_not_hidden(fixture_paths):
    reports = run_all(FIXTURE_DIR)
    for metrics in reports:
        assert metrics.abstention_by_channel, "abstention breakdown missing"
        assert 0.0 <= metrics.abstention_rate <= 1.0
        assert "latency_overhead" in metrics.to_dict()
        assert metrics.latency_overhead.get("status") == "skipped"


def test_licensed_confirm_fixture_expectations():
    metrics = run_fixture(FIXTURE_DIR / "football_licensed_confirm.json")
    assert metrics.final_state == "confirmed"
    assert metrics.replay_consistent
    assert metrics.moment_boundary_error_ns == 0
    assert metrics.outcome_accuracy == 1.0


def test_partial_fixture_abstains_outcome():
    metrics = run_fixture(FIXTURE_DIR / "football_partial_abstain.json")
    assert metrics.final_state == "partial"
    assert metrics.false_confirmed_claims == 0
    assert metrics.abstention_rate > 0
