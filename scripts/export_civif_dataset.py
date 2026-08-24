#!/usr/bin/env python3
"""Export civif-v0 coupling sidecars to JSONL (observation plane, local file).

  python scripts/export_civif_dataset.py clips/ dataset.jsonl
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qoresence.foundry.dataset import write_dataset  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 2:
        print("usage: export_civif_dataset.py <clips-dir> <out.jsonl>", file=sys.stderr)
        return 2
    result = write_dataset(args[1], clips_dir=args[0])
    print(f"OK {result['count']} -> {result['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
