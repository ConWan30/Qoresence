"""Observation eval metrics v0 — offline, replay-safe."""

from __future__ import annotations

from dataclasses import dataclass, field

from qoresence.observation.lifecycle import qualified_claim, replay_journal
from qoresence.observation.uncertainty import ALL_CHANNELS


@dataclass
class EvalMetrics:
    session_id: str
    false_confirmed_claims: int = 0
    moment_boundary_error_ns: int | None = None
    outcome_accuracy: float | None = None
    abstention_rate: float = 0.0
    evidence_coverage: float = 0.0
    replay_consistent: bool = True
    latency_overhead: dict = field(default_factory=lambda: {"status": "skipped", "reason": "no_hardware"})
    abstention_by_channel: dict = field(default_factory=dict)
    final_state: str | None = None
    revision_count: int = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "false_confirmed_claims": self.false_confirmed_claims,
            "moment_boundary_error_ns": self.moment_boundary_error_ns,
            "outcome_accuracy": self.outcome_accuracy,
            "abstention_rate": self.abstention_rate,
            "evidence_coverage": self.evidence_coverage,
            "replay_consistent": self.replay_consistent,
            "latency_overhead": self.latency_overhead,
            "abstention_by_channel": self.abstention_by_channel,
            "final_state": self.final_state,
            "revision_count": self.revision_count,
        }


def _count_false_confirmed(rows: list[dict]) -> int:
    false = 0
    for row in rows:
        record, evidence = row["record"], row["evidence"]
        if record.get("state") != "confirmed" or not record.get("claims"):
            continue
        if qualified_claim(evidence) is None:
            false += 1
    return false


def _abstention_stats(records: list[dict]) -> tuple[float, dict]:
    total = 0
    abstained = 0
    by_channel = {name: {"abstained": 0, "reported": 0} for name in ALL_CHANNELS}
    for record in records:
        channels = record.get("uncertainty_channels") or {}
        for name in ALL_CHANNELS:
            body = channels.get(name) or {}
            by_channel[name]["reported"] += 1
            total += 1
            if not body:
                abstained += 1
                by_channel[name]["abstained"] += 1
    rate = (abstained / total) if total else 0.0
    return rate, by_channel


def _evidence_coverage(rows: list[dict]) -> float:
    if not rows:
        return 0.0
    covered = sum(1 for row in rows if row["record"].get("evidence_ids"))
    return covered / len(rows)


def compute_metrics(
    rows: list[dict],
    *,
    session_id: str,
    labels: dict | None = None,
) -> EvalMetrics:
    labels = labels or {}
    metrics = EvalMetrics(session_id=session_id)
    metrics.false_confirmed_claims = _count_false_confirmed(rows)
    metrics.evidence_coverage = _evidence_coverage(rows)
    metrics.revision_count = len(rows)

    try:
        records = replay_journal(rows, session_id=session_id)
        metrics.replay_consistent = True
    except ValueError:
        metrics.replay_consistent = False
        records = [row["record"] for row in rows]

    if records:
        final = max(records, key=lambda r: (r.get("last_clock_ns", 0), r.get("revision", 0)))
        metrics.final_state = final.get("state")
        metrics.abstention_rate, metrics.abstention_by_channel = _abstention_stats(records)

        expected_end = labels.get("moment_boundary_end_ns")
        if expected_end is not None and final.get("end_ns") is not None:
            metrics.moment_boundary_error_ns = abs(int(final["end_ns"]) - int(expected_end))

        expected_outcome = labels.get("outcome_expected")
        if "outcome_expected" in labels:
            actual = final.get("outcome")
            metrics.outcome_accuracy = 1.0 if actual == expected_outcome else 0.0

        if labels.get("allow_confirmed") is False and metrics.final_state == "confirmed":
            metrics.false_confirmed_claims += 1

    return metrics
