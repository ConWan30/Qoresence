"""eval_session.py — replay a Qoresence session JSONL and report metrics.

Usage:
    python eval/eval_session.py logs/session_2026-08-06_direct_usb0_CLEAN.jsonl

Reports:
- football precision (no shooter false positives)
- average VLM latency and percentile histogram
- desync count observed during replay
- weighted verdict distribution from the fusion engine
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Suppress anomaly warning spam during deterministic replay.
logging.getLogger("qoresence.fusion.presence").setLevel(logging.ERROR)


def _load_events(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def eval_session(path: Path) -> dict[str, Any]:
    from qoresence.core import (
        FusionWeights,
        OutcomeConfig,
        RetinaEventBus,
        RetinaUnifiedConfig,
        SourceLobe,
    )
    from qoresence.fusion.presence import PresenceFusionEngine

    events = _load_events(path)
    if not events:
        raise ValueError(f"No events in {path}")

    session_id = events[0].get("session_id", "eval")
    head_ns = int(events[0].get("session_head_ns", 0) or 0)

    config = RetinaUnifiedConfig(
        session_id=session_id,
        session_head_ns=head_ns,
        fusion_weights=FusionWeights(),
        outcome=OutcomeConfig(enabled=True),
    )
    bus = RetinaEventBus(session_id=session_id, enable_ws=False)
    engine = PresenceFusionEngine(config, bus)

    reports: list = []

    def _report_callback(report):
        reports.append(report)

    engine.set_report_callback(_report_callback)

    visual_latencies: list[float] = []
    visual_categories: Counter = Counter()
    input_anomaly_counts: Counter = Counter()

    for event in events:
        etype = event.get("type")
        payload = event.get("payload", {})

        # Tally anomalies from the recorded presence_report events without
        # replaying them, so the metric reflects the original session state.
        if etype == "presence_report":
            for a in payload.get("anomalies", []):
                input_anomaly_counts[a.get("type", "unknown")] += 1
            continue

        source = SourceLobe(event.get("source_lobe", "streamer"))

        bus.emit_raw(
            source_lobe=source,
            event_type=etype,
            payload=payload,
            clock_ns_override=int(event.get("clock_ns", 0) or 0),
            session_head_ns=int(event.get("session_head_ns", 0) or 0),
        )

        if etype == "visual_context":
            visual_latencies.append(float(payload.get("latency_ms", 0.0) or 0.0))
            visual_categories[payload.get("game_category", "unknown")] += 1

    engine.stop()

    football_frames = visual_categories.get("football", 0)
    shooter_frames = visual_categories.get("shooter", 0)
    total_visual = sum(visual_categories.values())

    football_precision = 1.0
    if football_frames + shooter_frames > 0:
        football_precision = football_frames / (football_frames + shooter_frames)

    avg_latency = statistics.mean(visual_latencies) if visual_latencies else 0.0
    latency_histogram = {
        "p50": _percentile(visual_latencies, 50),
        "p95": _percentile(visual_latencies, 95),
        "p99": _percentile(visual_latencies, 99),
    }

    desync_count = input_anomaly_counts.get("temporal_desync", 0)

    verdict_counts: Counter = Counter()
    for r in reports:
        verdict_counts[r.weighted_verdict] += 1

    result = {
        "session_id": session_id,
        "events_replayed": len(events),
        "visual_context_frames": total_visual,
        "visual_category_counts": dict(visual_categories),
        "football_precision": round(football_precision, 4),
        "shooter_found": shooter_frames,
        "avg_vlm_latency_ms": round(avg_latency, 2),
        "latency_histogram_ms": {k: round(v, 2) for k, v in latency_histogram.items()},
        "desync_count": desync_count,
        "weighted_verdict_counts": dict(verdict_counts),
        "passed": football_precision == 1.0 and shooter_frames == 0 and avg_latency < 100.0,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay a Qoresence session JSONL and report metrics."
    )
    parser.add_argument("jsonl_path", type=Path, help="Path to session JSONL")
    args = parser.parse_args()

    if not args.jsonl_path.exists():
        print(f"Error: file not found: {args.jsonl_path}", file=sys.stderr)  # noqa: T201
        return 1

    result = eval_session(args.jsonl_path)
    print(json.dumps(result, indent=2))  # noqa: T201
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
