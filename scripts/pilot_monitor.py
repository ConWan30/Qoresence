#!/usr/bin/env python3
"""Standalone P0 pilot monitor. Never opens capture. Localhost only."""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qoresence.pilot.monitor import DEFAULT_URL, PilotMonitor  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Qoresence pilot monitor (localhost evidence)")
    p.add_argument("--url", default=DEFAULT_URL, help="Deck base URL (default 127.0.0.1:8765)")
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--out-dir", default="logs/pilot")
    p.add_argument("--duration", type=float, default=0.0, help="seconds; 0 = until SIGINT")
    p.add_argument("--warm-up", type=float, default=30.0)
    p.add_argument("--clips-dir", default="clips")
    args = p.parse_args()
    if not str(args.url).startswith("http://127.0.0.1") and not str(args.url).startswith(
        "http://localhost"
    ):
        print("pilot_monitor: localhost only", file=sys.stderr)
        return 2

    mon = PilotMonitor(
        args.url,
        interval_s=args.interval,
        out_dir=args.out_dir,
        clips_dir=args.clips_dir,
        warm_up_s=args.warm_up,
        duration_s=args.duration,
    )

    def _stop(_signum: int | None = None, _frame: object | None = None) -> None:
        mon.stop(timeout_s=2.0)

    signal.signal(signal.SIGINT, _stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _stop)
    mon.start()
    print(f"pilot_monitor writing {mon.session_path}", flush=True)
    thread = mon._thread
    if thread is not None:
        thread.join()
    if mon.closeout_md:
        print(mon.closeout_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
