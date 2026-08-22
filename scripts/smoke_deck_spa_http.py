#!/usr/bin/env python3
"""HTTP smoke: Deck glass SPA routes return 200, #root, and /assets/* 200.

Uses FastAPI TestClient (no live bind). Prefers vendored glass_spa when
glass/dist is absent (CI). Forces glass_spa candidate first so CI does not
depend on a local Vite build.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ASSET_REF = re.compile(r"""['"](/assets/[^'"]+)['"]""")
ROUTES = ("/deck.html", "/overlay.html", "/studio.html", "/mobile.html")

FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f" FAIL {msg}")
    FAILURES.append(msg)


def main() -> int:
    print("Deck SPA HTTP smoke")
    print("=" * 40)

    spa = ROOT / "qoresence" / "deck" / "glass_spa"
    if not (spa / "index.html").is_file():
        fail("qoresence/deck/glass_spa/index.html missing")
        print("=" * 40)
        return 1
    ok("vendored glass_spa present")

    import qoresence.deck.server as deck

    # Prefer packaged SPA for this smoke (CI has no glass/dist).
    deck._glass_candidates = lambda: [spa]  # type: ignore[method-assign]

    from fastapi.testclient import TestClient

    app = deck.create_app()
    client = TestClient(app)

    seen_assets: set[str] = set()
    for path in ROUTES:
        r = client.get(path)
        if r.status_code != 200:
            fail(f"GET {path} -> {r.status_code}")
            continue
        ok(f"GET {path} -> 200")
        body = r.text
        if 'id="root"' not in body and "id='root'" not in body:
            fail(f"{path} missing id=root")
        else:
            ok(f"{path} has #root")
        for ref in ASSET_REF.findall(body):
            seen_assets.add(ref)

    if not seen_assets:
        fail("no /assets/* refs found in HTML")
    for ref in sorted(seen_assets):
        ar = client.get(ref)
        if ar.status_code != 200:
            fail(f"GET {ref} -> {ar.status_code}")
        elif not ar.content:
            fail(f"GET {ref} empty body")
        else:
            ok(f"GET {ref} -> 200 ({len(ar.content)} bytes)")

    print("=" * 40)
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
