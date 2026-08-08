#!/usr/bin/env python3
"""Local release-hardening preflight (no network required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILURES: list[str] = []


def ok(msg: str) -> None:
    print(f"  OK  {msg}")


def fail(msg: str) -> None:
    print(f" FAIL {msg}")
    FAILURES.append(msg)


def main() -> int:
    print("Release hardening preflight")
    print("=" * 40)

    # 1. Deck loopback
    try:
        from qoresence.deck.server import DECK_HOST

        if DECK_HOST in ("127.0.0.1", "localhost", "::1"):
            ok(f"DECK_HOST={DECK_HOST}")
        else:
            fail(f"DECK_HOST is not loopback: {DECK_HOST!r}")
    except Exception as e:
        fail(f"import deck.server: {e}")

    # 2. Latency stats (disabled default)
    try:
        from qoresence.observability import get_latency_stats, record_latency, reset_latency_stats

        reset_latency_stats(enabled=False)
        st = get_latency_stats()
        record_latency("check", 1.0)
        s = st.summary()
        if s.get("enabled") is False and s.get("names") == {}:
            ok("LatencyStats disabled summary empty")
        else:
            fail(f"LatencyStats unexpected: {s}")
    except Exception as e:
        fail(f"latency stats: {e}")

    # 3. Required files
    required = [
        "docs/RELEASE_HARDENING.md",
        "qoresence/observability/latency_stats.py",
        "tests/test_security_localhost.py",
        "tests/test_soak_synthetic.py",
        ".github/workflows/ci-hardening.yml",
    ]
    for rel in required:
        p = ROOT / rel
        if p.is_file():
            ok(f"present {rel}")
        else:
            fail(f"missing {rel}")

    # 4. gitignore essentials
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").is_file() else ""
    for token in (".env", "logs/", "clips/", ".secrets"):
        if token in gi:
            ok(f"gitignore has {token}")
        else:
            fail(f"gitignore missing {token}")

    # 5. No default 0.0.0.0 in deck
    deck_src = (ROOT / "qoresence" / "deck" / "server.py").read_text(encoding="utf-8")
    for line in deck_src.splitlines():
        if line.strip().startswith("#"):
            continue
        if "DECK_HOST" in line and "0.0.0.0" in line:
            fail(f"DECK_HOST wildcard: {line.strip()}")
            break
    else:
        ok("deck server has no DECK_HOST=0.0.0.0")

    print("=" * 40)
    if FAILURES:
        print(f"{len(FAILURES)} failure(s)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
