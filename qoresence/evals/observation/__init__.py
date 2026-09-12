"""Observation engine evaluation — accuracy and abstention together."""

from .metrics import EvalMetrics, compute_metrics
from .runner import load_fixture, run_fixture

__all__ = ["EvalMetrics", "compute_metrics", "load_fixture", "run_fixture"]
