"""Exposure metrics for score-replay runs.

The exposure timeline is what the glass would have painted: a sorted list of
``(start_ns, pair_or_None)`` segments. Truth is the manifest's piecewise-
constant timeline. Comparing the two yields time-integral buckets plus
per-segment confirmation latency — the honest-digits cost of each policy.
"""

from __future__ import annotations

import itertools
from typing import Any


def exposure_at(timeline: list[tuple[int, Any]], ns: int) -> Any:
    pair = None
    for start, p in timeline:
        if start <= ns:
            pair = p
        else:
            break
    return pair


def _boundaries(timeline: list[tuple[int, Any]], truth: list[dict[str, Any]], end_ns: int) -> list[int]:
    pts = {0, end_ns}
    pts.update(s for s, _ in timeline if 0 <= s <= end_ns)
    pts.update(int(t["start_ns"]) for t in truth if 0 <= int(t["start_ns"]) <= end_ns)
    return sorted(pts)


def _truth_seg(truth: list[dict[str, Any]], ns: int) -> dict[str, Any] | None:
    seg = None
    for s in truth:
        if int(s["start_ns"]) <= ns:
            seg = s
        else:
            break
    return seg


def score_exposure(
    timeline: list[tuple[int, Any]],
    truth: list[dict[str, Any]],
    end_ns: int,
) -> dict[str, int]:
    """Integrate exposure vs truth over [0, end_ns].

    Buckets (ns): ``correct`` (painted pair matches readable truth),
    ``wrong`` (painted pair contradicts readable truth — includes stale
    holds), ``unexposed`` (nothing painted while truth readable — the safe
    abstention / `□–□` cost), ``ambiguous`` (truth absent or unreadable —
    excluded from right/wrong).
    """
    buckets = {"correct_ns": 0, "wrong_ns": 0, "unexposed_ns": 0, "ambiguous_ns": 0}
    pts = _boundaries(timeline, truth, end_ns)
    for a, b in itertools.pairwise(pts):
        width = b - a
        if width <= 0:
            continue
        seg = _truth_seg(truth, a)
        pair = exposure_at(timeline, a)
        if seg is None or not seg.get("readable", True):
            buckets["ambiguous_ns"] += width
        elif pair is None:
            buckets["unexposed_ns"] += width
        elif tuple(pair) == (seg.get("home_score"), seg.get("away_score")):
            buckets["correct_ns"] += width
        else:
            buckets["wrong_ns"] += width
    return buckets


def segment_latencies(
    timeline: list[tuple[int, Any]],
    truth: list[dict[str, Any]],
    end_ns: int,
) -> list[dict[str, Any]]:
    """Per readable truth segment: ns until exposure first matched it."""
    out: list[dict[str, Any]] = []
    for i, seg in enumerate(truth):
        if not seg.get("readable", True):
            continue
        start = int(seg["start_ns"])
        stop = int(truth[i + 1]["start_ns"]) if i + 1 < len(truth) else end_ns
        want = (seg.get("home_score"), seg.get("away_score"))
        first = None
        for t, pair in timeline:
            if t < start:
                continue
            if t >= stop:
                break
            if pair is not None and tuple(pair) == want:
                first = t
                break
        # exposure may already match at segment start (carried over)
        if first is None and exposure_at(timeline, start) == want:
            first = start
        out.append(
            {
                "start_ns": start,
                "pair": list(want),
                "confirmed": first is not None,
                "first_correct_latency_ns": (first - start) if first is not None else None,
            }
        )
    return out


def status_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return dict(sorted(counts.items()))
