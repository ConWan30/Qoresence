"""Stem audio resolve — never a laptop mic."""

from __future__ import annotations

from qoresence.stem.resolve import (
    is_capture_card_audio,
    is_denied_audio,
    resolve_audio_device,
)


def test_hdmi_card_audio_allowed():
    assert is_capture_card_audio("USB3.0 Audio") is True
    assert is_capture_card_audio("Elgato HD60 S+") is True
    assert is_capture_card_audio("Digital Audio (HDMI)") is True


def test_laptop_mic_denied():
    for name in (
        "Microphone (Realtek Audio)",
        "Headset Microphone",
        "Integrated Webcam",
        "Logitech BRIO",
        "Default",
    ):
        assert is_denied_audio(name) is True, name
        assert is_capture_card_audio(name) is False, name


def test_unplugged_never_opens_mic():
    devices = [
        (0, "Microphone (Realtek Audio)"),
        (1, "Headset Microphone"),
    ]
    assert resolve_audio_device(devices) is None


def test_resolve_prefers_hdmi_over_mic():
    devices = [
        (0, "Microphone (Realtek Audio)"),
        (1, "USB3.0 Audio"),
        (2, "Headset Microphone"),
    ]
    assert resolve_audio_device(devices) == (1, "USB3.0 Audio")


def test_unknown_name_is_not_card_audio():
    assert is_capture_card_audio("Something") is False
    assert resolve_audio_device([(0, "Something")]) is None
