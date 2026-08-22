#!/usr/bin/env python3
"""SPA land hygiene: smoke + size/shape gate for shipped Theater glass.

Checks the served Vite build under ``glass/dist`` (preferred) or
``qoresence/deck/glass_spa`` (packaged fallback). No network. No secrets.

Exit 0 on pass, 1 on fail.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Shape / size gates (fail-closed). Current ship ~401 KiB JS / ~25 KiB CSS.
MAX_JS_BYTES = 512_000
MAX_CSS_BYTES = 64_000
MIN_JS_BYTES = 80_000
MIN_CSS_BYTES = 4_000

ASSET_JS = re.compile(r"""['"](/assets/index-[A-Za-z0-9_-]+\.js)['"]""")
ASSET_CSS = re.compile(r"""['"](/assets/index-[A-Za-z0-9_-]+\.css)['"]""")
HASHED_JS = re.compile(r"^index-[A-Za-z0-9_-]+\.js$")
HASHED_CSS = re.compile(r"^index-[A-Za-z0-9_-]+\.css$")

FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f" FAIL {msg}")
    FAILURES.append(msg)


def _candidates() -> list[Path]:
    return [
        ROOT / "glass" / "dist",
        ROOT / "qoresence" / "deck" / "glass_spa",
    ]


def resolve_spa() -> Path | None:
    for p in _candidates():
        if (p / "index.html").is_file():
            return p
    return None


def check_spa(spa: Path) -> None:
    print(f"SPA root: {spa.relative_to(ROOT)}")
    html_path = spa / "index.html"
    html = html_path.read_text(encoding="utf-8")
    if 'id="root"' not in html and "id='root'" not in html:
        fail("index.html missing id=root")
    else:
        ok("index.html has #root")

    js_refs = ASSET_JS.findall(html)
    css_refs = ASSET_CSS.findall(html)
    if len(js_refs) != 1:
        fail(f"expected exactly 1 hashed JS module ref, found {js_refs!r}")
    else:
        ok(f"JS ref {js_refs[0]}")
    if len(css_refs) != 1:
        fail(f"expected exactly 1 hashed CSS ref, found {css_refs!r}")
    else:
        ok(f"CSS ref {css_refs[0]}")

    assets = spa / "assets"
    if not assets.is_dir():
        fail("assets/ directory missing")
        return

    for ref in js_refs:
        p = spa / ref.lstrip("/")
        if not p.is_file():
            fail(f"missing asset file {ref}")
            continue
        n = p.stat().st_size
        if n > MAX_JS_BYTES:
            fail(f"JS too large: {ref} = {n} bytes (max {MAX_JS_BYTES})")
        elif n < MIN_JS_BYTES:
            fail(f"JS too small / stub: {ref} = {n} bytes (min {MIN_JS_BYTES})")
        else:
            ok(f"JS size {ref} = {n} bytes")
        # Smoke markers that survive Vite minify on current ships.
        blob = p.read_text(encoding="utf-8", errors="ignore")
        for token in ("score_vlm_locked", "boardLocked"):
            if token in blob:
                ok(f"JS contains {token}")
            else:
                fail(f"JS bundle missing {token} marker")
        if "videoOptics" in blob:
            ok("JS contains videoOptics")
        else:
            ok("JS videoOptics absent (ok until optics SPA ships)")

    for ref in css_refs:
        p = spa / ref.lstrip("/")
        if not p.is_file():
            fail(f"missing asset file {ref}")
            continue
        n = p.stat().st_size
        if n > MAX_CSS_BYTES:
            fail(f"CSS too large: {ref} = {n} bytes (max {MAX_CSS_BYTES})")
        elif n < MIN_CSS_BYTES:
            fail(f"CSS too small / stub: {ref} = {n} bytes (min {MIN_CSS_BYTES})")
        else:
            ok(f"CSS size {ref} = {n} bytes")

    # Shape: only hashed index-* assets; no orphan piles
    on_disk_js = sorted(p.name for p in assets.glob("*.js"))
    on_disk_css = sorted(p.name for p in assets.glob("*.css"))
    for name in on_disk_js:
        if not HASHED_JS.match(name):
            fail(f"unexpected JS asset name {name!r}")
    for name in on_disk_css:
        if not HASHED_CSS.match(name):
            fail(f"unexpected CSS asset name {name!r}")
    if len(on_disk_js) > 3:
        fail(f"too many JS assets ({len(on_disk_js)}); expected a small Vite entry set")
    else:
        ok(f"JS asset count {len(on_disk_js)}")
    if len(on_disk_css) > 3:
        fail(f"too many CSS assets ({len(on_disk_css)}); expected a small Vite entry set")
    else:
        ok(f"CSS asset count {len(on_disk_css)}")

    # Referenced files must be a subset of on-disk
    for ref in js_refs:
        if Path(ref).name not in on_disk_js:
            fail(f"HTML JS ref not on disk: {ref}")
    for ref in css_refs:
        if Path(ref).name not in on_disk_css:
            fail(f"HTML CSS ref not on disk: {ref}")


def main() -> int:
    print("Glass SPA land hygiene (smoke + size/shape)")
    print("=" * 48)
    spa = resolve_spa()
    if spa is None:
        fail("no glass/dist or qoresence/deck/glass_spa with index.html")
    else:
        check_spa(spa)

    print("=" * 48)
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
