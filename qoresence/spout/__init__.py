"""Spout Glass — FrameHub PGM into OBS via Spout2 (default OFF).

Subscribe only. Never opens DShow. Never holds the streamer lock.
"""

from __future__ import annotations

from qoresence.spout.glass import (
    SpoutGlass,
    get_spout_glass,
    set_spout_glass,
    spout_health,
)

__all__ = [
    "SpoutGlass",
    "get_spout_glass",
    "set_spout_glass",
    "spout_health",
]
