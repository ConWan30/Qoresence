"""Capture device resolve — physical card by name, not sticky index."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from qoresence.lobes.streamer import resolve_capture_device

_GLASS_HARDWARE = (
    Path(__file__).resolve().parents[1] / "glass" / "src" / "lib" / "coupling" / "hardware.ts"
)


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


def test_unplugged_never_binds_generic_usb_video_device():
    """Laptop UVC often enumerates as 'USB Video Device' at index 0 after unplug."""
    from qoresence.lobes.streamer import _is_allowed_capture_name, _is_physical_card_name

    assert _is_allowed_capture_name("USB Video Device") is False
    assert _is_physical_card_name("USB Video Device") is False
    devices = [
        (0, "USB Video Device", False, "dshow"),
        (1, "OBS Virtual Camera", True, "dshow"),
    ]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(0, prefer_name="USB3.0 Video", allow_obs_vcam=False)
    assert got is None


def test_unplugged_never_opens_requested_index_webcam():
    devices = [(0, "Integrated Camera", False, "dshow")]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(0, prefer_name=None, allow_obs_vcam=False)
    assert got is None


def test_unknown_name_is_not_a_capture_card():
    from qoresence.lobes.streamer import _is_allowed_capture_name, _is_physical_card_name

    for name in ("Logitech BRIO", "HP Wide Vision", "USB2.0 HD UVC Device", "Something"):
        assert _is_allowed_capture_name(name) is False, name
        assert _is_physical_card_name(name) is False, name


def test_usb3_card_still_allowed():
    from qoresence.lobes.streamer import _is_allowed_capture_name, _is_physical_card_name

    assert _is_allowed_capture_name("USB3.0 Video") is True
    assert _is_physical_card_name("USB3.0 Video") is True


def test_resolve_obs_vcam_opt_in():
    devices = [
        (0, "720p HD Camera", False, "dshow"),
        (1, "OBS Virtual Camera", True, "dshow"),
    ]
    with patch("qoresence.lobes.streamer.list_dshow_devices", return_value=devices):
        got = resolve_capture_device(None, prefer_name=None, allow_obs_vcam=True)
    assert got == (1, "OBS Virtual Camera")


def test_glass_never_opens_default_camera_to_enumerate():
    """Unconstrained getUserMedia({video:true}) lights the laptop webcam."""
    src = _GLASS_HARDWARE.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("//"))
    assert "getUserMedia({ audio: false, video: true })" not in code
    assert "getUserMedia({video:true})" not in code.replace(" ", "")
