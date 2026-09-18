"""Score-replay runner: fold a manifest through each policy variant, offline.

Replays ``BoardObservation`` rows through the real ``ScoreRecheck`` state
machine — no VLM, TypeSafe, network, or capture hardware. Cached Jev verdicts
ride the manifest row (``jev.implausible_noul``); they only feed the injected
suspicion policy and can never license digits. Every judgment call is recorded
with its raw inputs and composed decision so policy comparison is auditable.

CLI::

    python -m qoresence.evals.scoreboard.runner [fixture_dir]
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qoresence.evals.scoreboard.manifest import (
    MANIFEST_SCHEMA,
    discover_manifests,
    load_manifest,
    to_board,
)
from qoresence.evals.scoreboard.metrics import (
    score_exposure,
    segment_latencies,
    status_counts,
)
from qoresence.evals.scoreboard.variants import (
    VARIANT_NAMES,
    jev_suspicion,
    jev_verdicts_by_seq,
    never_suspicious,
)
from qoresence.sync.digit_integrity import implausible_transition_reason
from qoresence.vision.score_recheck import ScoreRecheck

REPORT_SCHEMA = "qoresence-score-replay-report-0"


def _eval_ns(row: dict[str, Any]) -> int:
    return int(row.get("captured_ns") or 0) + int(row.get("arrival_delay_ns") or 0)


def _has_board(row: dict[str, Any]) -> bool:
    return type(row.get("home_score")) is int and type(row.get("away_score")) is int


def _make_policy(
    variant: str,
    observations: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    jev_threshold: float,
) -> Callable | None:
    """Suspicion fn per variant, wrapped to record every raw decision."""
    verdicts = jev_verdicts_by_seq(observations)

    def record(prior, cand, decided, extra):
        calls.append(
            {
                "prior_seq": prior.frame_seq,
                "cand_seq": cand.frame_seq,
                "prior_pair": list(prior.pair),
                "cand_pair": list(cand.pair),
                "decided_suspicious": decided,
                **extra,
            }
        )
        return decided

    if variant == "baseline":

        def baseline(prior, cand):
            return record(prior, cand, False, {"policy": "floor_only"})

        return baseline
    if variant == "deterministic":

        def det(prior, cand):
            reason = implausible_transition_reason(*prior.pair, *cand.pair)
            return record(
                prior, cand, reason is not None,
                {"policy": "delta_law", "reason": reason},
            )

        return det
    if variant == "typesafe":
        raw = jev_suspicion(verdicts, threshold=jev_threshold)

        def jev(prior, cand):
            noul = verdicts.get(cand.frame_seq)
            decided = raw(prior, cand)
            return record(
                prior, cand, decided,
                {
                    "policy": "jev_noul",
                    "noul": noul,
                    "threshold": jev_threshold,
                    "fallback": "delta_law" if noul is None else None,
                },
            )

        return jev
    if variant == "combined":
        jev = jev_suspicion(
            verdicts, threshold=jev_threshold, fallback=never_suspicious
        )

        def both(prior, cand):
            reason = implausible_transition_reason(*prior.pair, *cand.pair)
            noul = verdicts.get(cand.frame_seq)
            decided = (reason is not None) or jev(prior, cand)
            return record(
                prior, cand, decided,
                {
                    "policy": "delta_or_jev",
                    "reason": reason,
                    "noul": noul,
                    "threshold": jev_threshold,
                },
            )

        return both
    return None


def _replay_variant(
    manifest: dict[str, Any], variant: str, jev_threshold: float
) -> dict[str, Any]:
    rows = sorted(manifest["observations"], key=_eval_ns)
    truth = manifest["truth"]
    end_ns = manifest["end_ns"]
    calls: list[dict[str, Any]] = []
    recheck = None
    if variant != "legacy":
        recheck = ScoreRecheck(
            suspicion=_make_policy(variant, rows, calls, jev_threshold)
        )

    events: list[dict[str, Any]] = []
    timeline: list[tuple[int, Any]] = [(0, None)]
    exposed = None
    for row in rows:
        ns = _eval_ns(row)
        board = to_board(row)
        truth_pair = None
        seg = None
        for s in truth:
            if int(s["start_ns"]) <= ns:
                seg = s
            else:
                break
        if seg is not None:
            truth_pair = (seg.get("home_score"), seg.get("away_score"))
        readable = bool(seg and seg.get("readable", True)) if seg else False

        if variant == "legacy":
            status = "exposed" if _has_board(row) else "unparsed"
            if _has_board(row):
                exposed = board.pair
        else:
            if not _has_board(row):
                status = "no_board"
            else:
                status = recheck.evaluate(board, ns)
            if status == "accepted":
                exposed = board.pair
            elif status == "exhausted":
                # Runtime lets the triggering row through once bounds hit.
                exposed = board.pair

        if timeline[-1][1] != exposed:
            timeline.append((ns, exposed))
        events.append(
            {
                "frame_seq": board.frame_seq,
                "eval_ns": ns,
                "parsed_pair": list(board.pair) if _has_board(row) else None,
                "status": status,
                "exposed_after": list(exposed) if exposed else None,
                "truth_pair": list(truth_pair) if truth_pair else None,
                "readable": readable,
            }
        )

    # Paint bookkeeping: a "paint" is an exposure change while truth readable.
    paints = {"correct": 0, "wrong": 0, "held_events": 0}
    prev = None
    for e in events:
        cur = tuple(e["exposed_after"]) if e["exposed_after"] else None
        if cur != prev and cur is not None:
            if e["readable"] and e["truth_pair"]:
                if cur == tuple(e["truth_pair"]):
                    paints["correct"] += 1
                else:
                    paints["wrong"] += 1
        if e["status"] in ("recheck", "duplicate", "out_of_order", "stale",
                           "missing_evidence", "scene_unknown"):
            paints["held_events"] += 1
        prev = cur

    return {
        "variant": variant,
        "status_counts": status_counts(events),
        "exposure_ns": score_exposure(timeline, truth, end_ns),
        "paints": paints,
        "segments": segment_latencies(timeline, truth, end_ns),
        "judgment_calls": calls,
        "final_exposed": list(exposed) if exposed else None,
        "events": events,
        "_timeline": timeline,
    }


def _compare(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, r in results.items():
        out[name] = {
            "wrong_paints": r["paints"]["wrong"],
            "correct_paints": r["paints"]["correct"],
            "wrong_exposure_ns": r["exposure_ns"]["wrong_ns"],
            "unexposed_ns": r["exposure_ns"]["unexposed_ns"],
            "unconfirmed_segments": sum(
                1 for s in r["segments"] if not s["confirmed"]
            ),
        }
    return out


def run_manifest(
    manifest_or_path: dict[str, Any] | Path | str,
    *,
    variants: tuple[str, ...] = VARIANT_NAMES,
    jev_threshold: float = 0.7,
) -> dict[str, Any]:
    manifest = (
        load_manifest(manifest_or_path)
        if not isinstance(manifest_or_path, dict)
        else manifest_or_path
    )
    results = {
        v: _replay_variant(manifest, v, jev_threshold) for v in variants
    }
    # Replay parity: re-run the deterministic variant fresh and require the
    # same statuses + exposure. Guards against future nondeterminism.
    again = _replay_variant(manifest, "deterministic", jev_threshold)
    base = results.get("deterministic") or _replay_variant(
        manifest, "deterministic", jev_threshold
    )
    parity = (
        [e["status"] for e in again["events"]]
        == [e["status"] for e in base["events"]]
        and again["_timeline"] == base["_timeline"]
    )
    for r in results.values():
        r.pop("_timeline", None)
    return {
        "schema": REPORT_SCHEMA,
        "manifest_schema": MANIFEST_SCHEMA,
        "fixture": manifest.get("path"),
        "session_id": manifest["session_id"],
        "game_profile": manifest["game_profile"],
        "observations": len(manifest["observations"]),
        "end_ns": manifest["end_ns"],
        "deterministic_replay": parity,
        "variants": results,
        "comparison": _compare(results),
    }


def run_fixture_dir(
    directory: Path | str | None = None,
    *,
    variants: tuple[str, ...] = VARIANT_NAMES,
    jev_threshold: float = 0.7,
) -> dict[str, dict[str, Any]]:
    return {
        str(p): run_manifest(p, variants=variants, jev_threshold=jev_threshold)
        for p in discover_manifests(directory)
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    directory = args[0] if args else None
    reports = run_fixture_dir(directory)
    if not reports:
        sys.stderr.write("no score-replay fixtures found\n")
        return 1
    for path, report in reports.items():
        line = {
            "fixture": Path(path).name,
            "session_id": report["session_id"],
            "observations": report["observations"],
            "deterministic_replay": report["deterministic_replay"],
            "comparison": report["comparison"],
        }
        sys.stdout.write(json.dumps(line) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
