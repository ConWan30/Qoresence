#!/usr/bin/env python3
"""Pilot preflight — offline checks before a CFB session.

Exit 0: soft success (imports + Deck host loopback).
Exit 1: missing package or non-loopback DECK_HOST.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print("Qoresence pilot preflight")
    print(f"  repo: {REPO_ROOT}")

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    try:
        import qoresence  # noqa: F401
    except ImportError as e:
        print(f"FAIL: cannot import qoresence ({e})")
        print('  hint: cd repo root; pip install -e ".[monitor]"')
        return 1
    print("  import qoresence: OK")

    deck_server = REPO_ROOT / "qoresence" / "deck" / "server.py"
    if not deck_server.is_file():
        print(f"FAIL: missing {deck_server}")
        return 1
    print("  deck server file: OK")

    try:
        from qoresence.deck.server import DECK_HOST
    except Exception as e:
        print(f"FAIL: cannot import DECK_HOST ({e})")
        return 1

    host = str(DECK_HOST or "").strip().lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(f"FAIL: DECK_HOST={DECK_HOST!r} is not loopback (pilot requires local bind)")
        return 1
    print(f"  DECK_HOST={DECK_HOST!r}: OK (loopback)")

    try:
        from qoresence.lobes.controller import list_controllers

        pads = list_controllers()
        if pads:
            shown = ", ".join(
                f"{c.get('product') or 'pad'} vid={int(c.get('vid') or 0):04x} pid={int(c.get('pid') or 0):04x}"
                for c in pads[:4]
            )
            print(f"  DualSense listed: {shown}")
        else:
            print("  DualSense listed: none — lobe will wait for USB/BT plug-in")
    except Exception as e:
        print(f"  DualSense enumerate skipped: {e}")

    print("")
    print("Next steps:")
    print("  python -m qoresence.cli --streamer-list")
    print("  python -m qoresence.cli --play --deck --monitor --controller --streamer-fps 60")
    print("  # leave that window running; in a NEW PowerShell:")
    print("  #   $h = Invoke-RestMethod http://127.0.0.1:8765/health")
    print('  #   Write-Host "has_frame=$($h.state.video.has_frame)"')
    print("  #   Start-Process http://127.0.0.1:8765/deck.html")
    print("  # Deck is a browser page — CLI does not open it for you.")
    print("  docs: docs/CAPTURE_OWNERSHIP.md · docs/PILOT_SESSION.md")
    print("")
    print("preflight: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
