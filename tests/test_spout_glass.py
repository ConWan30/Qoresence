"""Spout Glass — default OFF, subscribe-only, stub sender on non-Windows."""

from __future__ import annotations

import numpy as np

from qoresence.monitor.frame_hub import FrameHub
from qoresence.spout.glass import SpoutGlass, set_spout_glass, spout_health
from qoresence.spout.sender import StubSpoutSender, create_sender, sender_probe


def test_create_sender_non_windows_is_stub() -> None:
    s = create_sender("QoresencePGM")
    assert s.name == "QoresencePGM"
    assert "stub" in s.backend or s.backend == "spoutgl"


def test_sender_probe_has_platform() -> None:
    p = sender_probe()
    assert "platform" in p
    assert "spout_available" in p


def test_spout_glass_publishes_from_framehub_stub() -> None:
    hub = FrameHub()
    stub = StubSpoutSender(name="TestPGM")
    glass = SpoutGlass(sender_name="TestPGM", target_hz=120.0, sender=stub)
    from qoresence.monitor import frame_hub as fh

    old = fh._hub
    fh._hub = hub
    try:
        set_spout_glass(glass)
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        frame[:] = (0, 128, 255)
        hub.publish(frame, clock_ns=111, seq=1)
        glass._tick()
        assert stub.sends == 1
        h = glass.health()
        assert h["published"] == 1
        assert h["last_frame_seq"] == 1
        assert h["last_clock_ns"] == 111
        glass._tick()
        assert stub.sends == 1
        hub.publish(frame, clock_ns=222, seq=2)
        glass._tick()
        assert stub.sends == 2
        assert glass.health()["last_clock_ns"] == 222
    finally:
        set_spout_glass(None)
        fh._hub = old


def test_spout_health_off_when_unset() -> None:
    set_spout_glass(None)
    h = spout_health()
    assert h["enabled"] is False


def test_cli_help_lists_spout_glass() -> None:
    # Avoid full cli import graph in unit CI; flag text must exist in cli.py.
    from pathlib import Path

    src = Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "--spout-glass" in src
    assert "--spout-name" in src
    assert "Optional Spout Glass" in src
    assert "Not implied by --play" in src or "not implied by --play" in src.lower()
