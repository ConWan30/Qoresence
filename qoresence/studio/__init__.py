"""Qoresence Studio — post-session Ghost Cut and optional LTX plugin.

Ghost Cut edits the local HDMI clip with chapter / score / button evidence.
LTX remains optional. Everything here is default-off and never blocks capture.
"""

from __future__ import annotations

from .frame_selector import FrameSelector
from .ghost_cut import GhostCutResult, cut_highlight
from .ltx_client import LtxClient, LtxJob, UploadResult, normalize_duration
from .prompt_engine import STYLE_LOCK, PromptEngine, RenderPayload
from .receipt import ReelReceipt, write_receipt
from .reel_queue import ReelQueue, RenderJob, reset_reel_queue
from .render_command import render_reels

__all__ = [
    "LtxClient",
    "LtxJob",
    "UploadResult",
    "normalize_duration",
    "STYLE_LOCK",
    "PromptEngine",
    "RenderPayload",
    "ReelReceipt",
    "write_receipt",
    "ReelQueue",
    "RenderJob",
    "reset_reel_queue",
    "FrameSelector",
    "GhostCutResult",
    "cut_highlight",
    "render_reels",
]
