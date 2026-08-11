"""Remove `# type: ignore` comments mypy flags as unused (batch hygiene helper).

Usage:
    python scripts/clean_unused_ignores.py <mypy_output_file>

Reads the output of `mypy --show-error-codes` and strips trailing
`# type: ignore[...]` comments from any line flagged `unused-ignore`.
Removing an *unused* ignore cannot alter mypy's verdict, so this is a
mechanical, revert-safe cleanup. Re-run mypy afterwards to confirm.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_IGNORE_RE = re.compile(r"\s*#\s*type:\s*ignore(?:\[[^\]]*\])?\s*$")
_FLAG_RE = re.compile(r"^(.+?):(\d+): error: .*unused-ignore")


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else Path("mypy.txt")
    hits: list[tuple[Path, int]] = []
    for line in src.read_text(encoding="utf-8").splitlines():
        m = _FLAG_RE.match(line)
        if m:
            hits.append((Path(m.group(1)), int(m.group(2))))

    changed = 0
    for rel, lineno in hits:
        p = ROOT / rel
        if not p.exists():
            print(f"skip missing: {rel}", file=sys.stderr)
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        idx = lineno - 1
        if not (0 <= idx < len(lines)):
            continue
        new = _IGNORE_RE.sub("", lines[idx]).rstrip()
        if new != lines[idx]:
            lines[idx] = new
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
            changed += 1
            print(f"cleaned {rel}:{lineno}")

    print(f"done: {len(hits)} flagged, {changed} cleaned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
