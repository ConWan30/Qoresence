"""Novel WebRTC LIVE — FrameHub → browser, no second DShow open.

Same rule as Retina Monitor / IVC: streamer already owns BGR frames.
This module only *subscribes* and encodes for RTCPeerConnection.

Optional dep: ``pip install aiortc av`` (extra ``webrtc``).
Localhost-first; no STUN required for 127.0.0.1.
"""

from __future__ import annotations

import asyncio
import fractions
import logging
import time
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

try:
    from aiortc import (
        RTCPeerConnection,
        RTCSessionDescription,
        VideoStreamTrack,
    )
    from av import VideoFrame

    _HAS_AIORTC = True
except ImportError:  # pragma: no cover
    RTCPeerConnection = None  # type: ignore[misc, assignment]
    RTCSessionDescription = None  # type: ignore[misc, assignment]
    VideoStreamTrack = object  # type: ignore[misc, assignment]
    VideoFrame = None  # type: ignore[misc, assignment]
    _HAS_AIORTC = False


def webrtc_available() -> bool:
    return bool(_HAS_AIORTC)


# Active peer connections (close on disconnect)
_pcs: set[Any] = set()


def stats() -> dict[str, Any]:
    return {
        "available": webrtc_available(),
        "peers": len(_pcs),
        "source": "frame_hub",  # never second capture
        "note": "install: pip install 'qoresence[webrtc]' or aiortc av",
    }


if _HAS_AIORTC:

    class FrameHubVideoTrack(VideoStreamTrack):  # type: ignore[misc]
        """Pull latest FrameHub BGR → WebRTC VideoFrame (no DShow open)."""

        kind = "video"

        def __init__(self, target_fps: float = 60.0, max_width: int = 1280) -> None:
            super().__init__()
            self.target_fps = max(5.0, min(60.0, float(target_fps)))
            self.max_width = int(max_width)
            self._pts = 0
            self._time_base = fractions.Fraction(1, int(self.target_fps))
            self._last_seq = -1
            self._black: np.ndarray | None = None
            self._frames_sent = 0
            self._interval = 1.0 / self.target_fps
            self._last_send = 0.0

        async def recv(self) -> Any:
            # Pull the latest FrameHub frame FIRST, then pace. This minimizes
            # latency — the frame is as fresh as possible when we encode it.
            img = self._pull_bgr()
            if img is None:
                img = self._placeholder()
            # Pace to target_fps using a wall-clock latch (not a blind sleep)
            now = time.monotonic()
            elapsed = now - self._last_send
            wait = self._interval - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_send = time.monotonic()
            # even dims for encoders
            h, w = img.shape[:2]
            if w % 2 or h % 2:
                img = img[: h - (h % 2), : w - (w % 2)]
            frame = VideoFrame.from_ndarray(img, format="bgr24")
            frame.pts = self._pts
            frame.time_base = self._time_base
            self._pts += 1
            self._frames_sent += 1
            return frame

        def _pull_bgr(self) -> np.ndarray | None:
            try:
                from qoresence.monitor.frame_hub import get_latest, get_latest_stamp

                st = get_latest_stamp()
                if not st.get("has_frame"):
                    return None
                seq = int(st.get("seq") or 0)
                # Always take latest (even if same seq once) so first frame paints
                fr = get_latest()
                if fr is None:
                    return None
                self._last_seq = seq
                return self._downscale(fr)
            except Exception as e:
                log.debug("FrameHubVideoTrack pull: %s", e)
                return None

        def _downscale(self, bgr: np.ndarray) -> np.ndarray:
            try:
                import cv2

                h, w = bgr.shape[:2]
                if self.max_width > 0 and w > self.max_width:
                    scale = self.max_width / float(w)
                    nh = max(2, int(h * scale) & ~1)
                    nw = self.max_width if self.max_width % 2 == 0 else self.max_width - 1
                    return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
                return bgr
            except Exception:
                return bgr

        def _placeholder(self) -> np.ndarray:
            if self._black is None:
                self._black = np.zeros((360, 640, 3), dtype=np.uint8)
                # dim gold bar so user knows track is alive without frames
                self._black[170:190, 200:440] = (40, 160, 200)
            return self._black


async def handle_offer(
    sdp: str,
    type_: str = "offer",
    *,
    target_fps: float = 60.0,
    max_width: int = 1280,
) -> dict[str, str]:
    """Client offer → server answer with FrameHub video track."""
    if not _HAS_AIORTC:
        raise RuntimeError(
            "aiortc not installed. Run: pip install aiortc av  "
            "or pip install -e \".[webrtc]\""
        )

    pc = RTCPeerConnection()
    _pcs.add(pc)

    @pc.on("connectionstatechange")
    async def _on_state() -> None:
        log.info("WebRTC peer state=%s", pc.connectionState)
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await _close_pc(pc)

    track = FrameHubVideoTrack(target_fps=target_fps, max_width=max_width)
    pc.addTrack(track)

    await pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=type_))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    await _wait_ice_complete(pc, timeout_s=4.0)

    assert pc.localDescription is not None
    return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}


async def _wait_ice_complete(pc: Any, timeout_s: float = 4.0) -> None:
    if pc.iceGatheringState == "complete":
        return
    done = asyncio.Event()

    @pc.on("icegatheringstatechange")
    def _check() -> None:
        if pc.iceGatheringState == "complete":
            done.set()

    try:
        await asyncio.wait_for(done.wait(), timeout=timeout_s)
    except TimeoutError:
        log.debug("WebRTC ICE gathering timeout — returning partial candidates")


async def _close_pc(pc: Any) -> None:
    try:
        await pc.close()
    except Exception:
        pass
    _pcs.discard(pc)


async def close_all() -> None:
    for pc in list(_pcs):
        await _close_pc(pc)
