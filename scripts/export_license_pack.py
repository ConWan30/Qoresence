#!/usr/bin/env python3
"""CLI entry for Frame License Bureau v0 export (thin wrapper)."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from a checkout without install.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from qoresence.license_bureau import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
