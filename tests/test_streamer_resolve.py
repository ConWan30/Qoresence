"""Capture device resolve — physical card by name, not sticky index."""

from __future__ import annotations

from unittest.mock import patch

from qoresence.lobes.streamer import resolve_capture_device


def test_resolve_prefers_usb3_over_webcam_and_vcam():
    devices = [
        (0, "720p HD Camera", False, "dshow"),
        (1, "USB3.0 Video", True, "dshow"),
        (2, "OBS Virtual Camera", True, "dshow"),
    ]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(0, prefer_name=None, allow_obs_vcam=False)
    assert got == (1, "USB3.0 Video")


def test_resolve_sticky_name_after_index_shift():
    # Card was idx 0, after replug webcam is 0 and card is 2
    devices = [
        (0, "720p HD Camera", False, "dshow"),
        (1, "OBS Virtual Camera", True, "dshow"),
        (2, "USB3.0 Video", True, "dshow"),
    ]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(0, prefer_name="USB3.0 Video", allow_obs_vcam=False)
    assert got == (2, "USB3.0 Video")


def test_resolve_none_when_unplugged():
    devices = [
        (0, "720p HD Camera", False, "dshow"),
        (1, "OBS Virtual Camera", True, "dshow"),
    ]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(None, prefer_name="USB3.0 Video", allow_obs_vcam=False)
    assert got is None


def test_resolve_obs_vcam_opt_in():
    devices = [
        (0, "720p HD Camera", False, "dshow"),
        (1, "OBS Virtual Camera", True, "dshow"),
    ]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(None, prefer_name=None, allow_obs_vcam=True)
    assert got == (1, "OBS Virtual Camera")
