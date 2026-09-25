#!/usr/bin/env python3
"""Clip-excision pilot gate: score Cut Receipts against hand labels.

    python scripts/excise_pilot_gate.py --clips clips --init-labels labels.json
    python scripts/excise_pilot_gate.py --clips clips --labels labels.json \
        --health logs/pilot/*.json

Exit codes: 0 pass, 1 fail, 2 insufficient evidence. Never changes a default.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qoresence.vision import excise_pilot as ep  # noqa: E402

OUT_DIR = REPO_ROOT / "logs" / "pilot"
EXIT = {"pass": 0, "fail": 1, "insufficient": 2}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--clips", default="clips", help="Clip folder with *.mp4 + *.cut.json")
    ap.add_argument("--labels", help="Labels JSON to score against")
    ap.add_argument("--init-labels", metavar="PATH", help="Write a blank labels file and exit")
    ap.add_argument("--health", nargs="*", default=[], help="Saved /health or pilot_snapshot JSON")
    ap.add_argument("--model", help="Pinned Jev model id (default: QORESENCE_EXCISE_MODEL)")
    ap.add_argument("--min-clips", type=int, default=ep.GATE_MIN_CLIPS)
    ap.add_argument("--out", help="Report path (default: logs/pilot/excise_gate_<ts>.json)")
    args = ap.parse_args(argv)

    if args.init_labels:
        dst = Path(args.init_labels)
        if dst.exists():
            print(f"refusing to overwrite {dst}")
            return 2
        tpl = ep.init_labels(args.clips)
        dst.write_text(json.dumps(tpl, indent=2), encoding="utf-8")
        print(f"wrote {len(tpl['clips'])} blank label(s) → {dst}")
        return 0
    if not args.labels:
        ap.error("--labels or --init-labels is required")

    report = ep.evaluate(
        args.clips,
        ep.load_labels(args.labels),
        health_files=args.health,
        pinned_model=args.model,
        min_clips=args.min_clips,
    )
    if args.out:
        out = Path(args.out)
    else:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out = OUT_DIR / f"excise_gate_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    s = report["summary"]
    print(f"excise pilot gate: {report['verdict'].upper()}  ({report['policy_version']})")
    print(
        f"  clips scored {s['clips_scored']}/{s['clips_labelled']}  "
        f"football-with-dead {s['football_clips_with_dead']}  kinds {s['dead_kinds_seen']}"
    )
    print(
        f"  over-cut {s['over_cut_s']}s  under-cut {s['under_cut_s']}s  "
        f"dead removed {s['dead_removed_fraction']}"
    )
    c = report["clicks"]
    print(
        f"  suggest-accept {c['suggest_accept_rate']}  vetoes {len(c['vetoes'])}  "
        f"age_s max {s['age_s_max']} ({s['age_s_samples']} samples)"
    )
    for f in report["failures"]:
        print(f"  FAIL: {f}")
    for g in report["gaps"]:
        print(f"  GAP:  {g}")
    print(f"  report → {out}")
    return EXIT[report["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
