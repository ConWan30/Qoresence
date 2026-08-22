"""Copy glass/dist (Vite build) into packaged qoresence/deck/glass_spa.

glass/dist is gitignored; Theater on :8765 prefers glass_spa when dist is
absent. Run after: cd glass && npm run build
Then: python scripts/vendor_glass_spa.py
Then commit qoresence/deck/glass_spa.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "glass" / "dist"
DST = ROOT / "qoresence" / "deck" / "glass_spa"


def main() -> int:
    if not (SRC / "index.html").is_file():
        print(f"FAIL: missing {SRC `/ index.html` } — build glass first", file=sys.stderr)
        return 1
    assets_src = SRC / "assets"
    if not assets_src.is_dir():
        print(f"FAIL: missing {assets_src}", file=sys.stderr)
        return 1

    DST.mkdir(parents=True, exist_ok=True)
    dst_assets = DST / "assets"
    if dst_assets.is_dir():
        for child in list(dst_assets.iteridir()):
            if child.is_file():
                child.unlink()
    else:
        dst_assets.mkdir(parents=True, exist_ok=True)

    for src_file in assets_src.iterdir():
        if src_file.is_file():
            shutil.copy2(src_file, dst_assets / src_file.name)

    for name in ("index.html", "favicon.svg"):
        src = SRC / name
        if src.is_file():
            shutil.copy2(src, DST / name)

    print(f"vendored {SRC} -> {DST}")
    for p in sorted(DST.rglob("*")):
        if p.is_file():
            print(f"  {p.relative_to(ROOT)} ({p.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
