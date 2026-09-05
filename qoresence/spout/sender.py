"""Spout2 sender backends. Windows first; stub elsewhere for CI."""

from __future__ import annotations

import logging
import sys
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)

DEFAULT_SENDER_NAME = "QoresencePGM"


class SpoutSender(Protocol):
    def send(self, frame_bgr: np.ndarray) -> bool: ...

    def close(self) -> None: ...

    @property
    def backend(self) -> str: ...

    @property
    def name(self) -> str: ...


class StubSpoutSender:
    """No-op sender for non-Windows / missing SpoutGL. Counts sends for tests."""

    def __init__(self, name: str = DEFAULT_SENDER_NAME, reason: str = "stub") -> None:
        self._name = name
        self._reason = reason
        self.sends = 0

    @property
    def backend(self) -> str:
        return f"stub:{self._reason}"

    @property
    def name(self) -> str:
        return self._name

    def send(self, frame_bgr: np.ndarray) -> bool:
        if frame_bgr is None or not hasattr(frame_bgr, "shape"):
            return False
        self.sends += 1
        return True

    def close(self) -> None:
        return None


class WindowsSpoutGLSender:
    """Spout2 via SpoutGL when installed on Windows."""

    def __init__(self, name: str = DEFAULT_SENDER_NAME) -> None:
        if sys.platform != "win32":
            raise RuntimeError("WindowsSpoutGLSender requires win32")
        import SpoutGL  # type: ignore
        from SpoutGL.enums import GL  # type: ignore

        self._SpoutGL = SpoutGL
        self._GL = GL
        self._name = name
        self._sender = SpoutGL.SpoutSender()
        self._sender.setSenderName(name)
        self._width = 0
        self._height = 0

    @property
    def backend(self) -> str:
        return "spoutgl"

    @property
    def name(self) -> str:
        return self._name

    def send(self, frame_bgr: np.ndarray) -> bool:
        if frame_bgr is None or len(getattr(frame_bgr, "shape", ())) < 2:
            return False
        h, w = int(frame_bgr.shape[0]), int(frame_bgr.shape[1])
        # Spout expects RGB contiguous
        try:
            import cv2

            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        except Exception:
            rgb = frame_bgr[:, :, ::-1].copy() if frame_bgr.ndim == 3 else frame_bgr
        rgb = np.ascontiguousarray(rgb)
        ok = bool(
            self._sender.sendImage(
                rgb,
                w,
                h,
                self._GL.RGB,
                False,
                0,
            )
        )
        self._width, self._height = w, h
        return ok

    def close(self) -> None:
        try:
            self._sender.releaseSender()
        except Exception as e:
            log.debug("Spout releaseSender: %s", e)


def create_sender(name: str = DEFAULT_SENDER_NAME) -> SpoutSender:
    """Pick Windows SpoutGL when available; else stub (fail-closed, not crash)."""
    if sys.platform != "win32":
        return StubSpoutSender(name=name, reason="non-windows")
    try:
        return WindowsSpoutGLSender(name=name)
    except Exception as e:
        log.warning(
            "Spout Glass: SpoutGL unavailable (%s). Using stub. "
            "Install SpoutGL on Windows for OBS Spout Capture.",
            e,
        )
        return StubSpoutSender(name=name, reason="spoutgl-missing")


def sender_probe() -> dict[str, Any]:
    """Describe what create_sender would pick without opening a long-lived sender."""
    if sys.platform != "win32":
        return {"platform": sys.platform, "backend": "stub:non-windows", "spout_available": False}
    try:
        import SpoutGL  # noqa: F401

        return {"platform": "win32", "backend": "spoutgl", "spout_available": True}
    except Exception as e:
        return {
            "platform": "win32",
            "backend": "stub:spoutgl-missing",
            "spout_available": False,
            "error": str(e)[:200],
        }
