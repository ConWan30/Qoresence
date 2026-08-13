"""Extract a high-quality PNG from a local clip at a chapter timestamp."""

from __future__ import annotations

import logging
from pathlib import Path

import cv2

log = logging.getLogger(__name__)


class FrameSelector:
    """Pick and extract a representative frame from an MP4."""

    def __init__(self, cache_dir: str | Path | None = None):
        self.cache_dir = Path(cache_dir) if cache_dir else None

    def extract_png(
        self,
        clip_path: str | Path,
        t_s: float,
        output_path: str | Path | None = None,
        *,
        max_dimension: int = 1920,
        fallback_to_first: bool = True,
    ) -> Path | None:
        """Decode a frame at t_s and write a PNG. Returns output path or None."""
        clip_path = Path(clip_path)
        if not clip_path.is_file():
            log.warning("FrameSelector: clip not found: %s", clip_path)
            return None

        cap = cv2.VideoCapture(str(clip_path))
        if not cap.isOpened():
            log.warning("FrameSelector: cannot open clip: %s", clip_path)
            return None

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            cap.release()
            return None

        frame_idx = max(0, min(total - 1, int(t_s * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, bgr = cap.read()
        cap.release()

        if not ok or bgr is None:
            if not fallback_to_first:
                return None
            log.debug("FrameSelector: fallback to first frame")
            cap = cv2.VideoCapture(str(clip_path))
            ok, bgr = cap.read()
            cap.release()
            if not ok or bgr is None:
                return None

        # Keep long edge bounded for overlay compositing.
        h, w = bgr.shape[:2]
        scale = 1.0
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

        if output_path is None:
            if self.cache_dir:
                out_dir = self.cache_dir / clip_path.stem
            else:
                out_dir = clip_path.parent / (clip_path.stem + "_cut")
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = out_dir / f"frame_{frame_idx:06d}.png"
        else:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            cv2.imwrite(str(output_path), bgr)
            log.info("FrameSelector: wrote %s (%dx%d)", output_path, bgr.shape[1], bgr.shape[0])
            return output_path
        except Exception as e:
            log.warning("FrameSelector: write failed: %s", e)
            return None
