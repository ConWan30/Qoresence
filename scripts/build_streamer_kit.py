"""Zip streamer-kit/ into dist/qoresence-streamer-kit.zip (release-ready, not published)."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "streamer-kit"


def build(out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(KIT.rglob("*")):
            if path.is_file():
                zf.write(path, Path("qoresence-streamer-kit") / path.relative_to(KIT))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "qoresence-streamer-kit.zip")
    print(build(ap.parse_args().out))


if __name__ == "__main__":
    main()
