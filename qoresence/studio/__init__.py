"""Qoresence Studio — post-session Ghost Cut.

Cuts a local HDMI clip with chapter / score / timed button ghosts.
Default-off. Never blocks the live capture path. No paid video API.
"""

from __future__ import annotations

from .frame_selector import FrameSelector
from .ghost_cut import GhostCutResult, GhostEvent, cut_highlight, held_at, load_button_timeline
from .receipt import ReelReceipt, write_receipt
from .reel_queue import ReelQueue, RenderJob, reset_reel_queue
from .render_command import render_reels

__all__ = [
    "FrameSelector",
    "GhostCutResult",
    "GhostEvent",
    "cut_highlight",
    "held_at",
    "load_button_timeline",
    "ReelReceipt",
    "write_receipt",
    "ReelQueue",
    "RenderJob",
    "reset_reel_queue",
    "render_reels",
]
