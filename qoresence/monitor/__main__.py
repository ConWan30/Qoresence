"""python -m qoresence.monitor — open Retina Monitor (play stack must be same process).

Prefer: python -m qoresence.cli --play --deck --monitor ...
Standalone entry only works if something else is already publishing to FrameHub
in this process (normally not). This entrypoint starts a viewer that waits for
frames and documents the preferred CLI.
"""

from __future__ import annotations

import logging
import sys


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    log = logging.getLogger("qoresence.monitor")
    log.info(
        "Prefer: python -m qoresence.cli --play --deck --monitor --streamer-device <N>. "
        "Standalone viewer waits on FrameHub (empty unless in-process streamer)."
    )
    try:
        from qoresence.monitor.window import run_monitor
    except Exception as e:
        print(f"Retina Monitor unavailable: {e}", file=sys.stderr)  # noqa: T201
        print("Install: pip install 'qoresence[monitor]'", file=sys.stderr)  # noqa: T201
        sys.exit(1)
    run_monitor()


if __name__ == "__main__":
    main()
