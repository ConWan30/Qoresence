"""Qoresence Studio — optional post-session generative-video rendering.

Foundry Reels turns local clips + causal receipts into cinematic LTX videos.
Everything here is default-off and never blocks the live capture path.
"""

from __future__ import annotations

from .frame_selector import FrameSelector
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
    "render_reels",
]
