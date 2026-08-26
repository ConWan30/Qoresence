#!/usr/bin/env python3
"""Private haptic corroboration from session logs. Observation plane only.

  python scripts/haptic_corroboration.py logs/haptic/sess.jsonl
  python scripts/haptic_corroboration.py logs/haptic/sess.jsonl --civif logs/civif/sess.jsonl
  python scripts/haptic_corroboration.py logs/haptic/sess.jsonl --clips clips/

Does not mint haptics_confirmed. Does not invent scores or button names.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qoresence.sync.haptic_metrics import session_report  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Private haptic corroboration metrics")
    p.add_argument("haptic_jsonl", type=Path, help="logs/haptic/*.jsonl")
    p.add_argument("--civif", type=Path, default=None, help="CIVIF tick JSONL")
    p.add_argument("--clips", type=Path, default=None, help="clips/ dir or *.coupling.json")
    p.add_argument("--window-ms", type=float, default=120.0)
    args = p.parse_args(argv)
    if not args.haptic_jsonl.is_file():
        print(f"missing haptic jsonl: {args.haptic_jsonl}", file=sys.stderr)
        return 2
    report = session_report(
        args.haptic_jsonl,
        civif_jsonl=args.civif,
        clips_dir=args.clips,
        window_ms=float(args.window_ms),
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
