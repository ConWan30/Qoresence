#!/usr/bin/env python3
"""Validate CIVIF v0 coupling sidecars (clips/*.coupling.json).

Empty DualSense on this host is valid. Invented scores or non-monotonic
input clocks fail.

Usage:
  python scripts/validate_coupling.py clips/hdmi_clip_foo.coupling.json
  python scripts/validate_coupling.py clips/
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qoresence.core.coupled_event import validate_coupling  # noqa: E402


def _files(arg: Path) -> list[Path]:
    if arg.is_file():
        return [arg]
    if arg.is_dir():
        return sorted(arg.glob("*.coupling.json"))
    return []


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: validate_coupling.py <file-or-dir>", file=sys.stderr)
        return 2
    paths: list[Path] = []
    for a in args:
        paths.extend(_files(Path(a)))
    if not paths:
        print("no *.coupling.json found", file=sys.stderr)
        return 2
    failed = 0
    for p in paths:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"FAIL {p}: {e}")
            failed += 1
            continue
        errs = validate_coupling(data)
        if errs:
            failed += 1
            print(f"FAIL {p.name}: {'; '.join(errs)}")
        else:
            print(f"OK   {p.name}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
