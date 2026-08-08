"""WebRTC hub — available flag + import without aiortc crash."""

from __future__ import annotations

from qoresence.deck import webrtc_hub


def test_stats_shape():
    s = webrtc_hub.stats()
    assert "available" in s
    assert s.get("source") == "frame_hub"
    assert "peers" in s


def test_unavailable_handle_offer_raises():
    if webrtc_hub.webrtc_available():
        return  # skip when aiortc installed
    import asyncio

    import pytest

    with pytest.raises(RuntimeError):
        asyncio.run(webrtc_hub.handle_offer("v=0", "offer"))
