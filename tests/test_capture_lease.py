"""Single-open capture lease — second process must not share the card."""

from __future__ import annotations

import os

import pytest

from qoresence.capture.lease import (
    CaptureLeaseError,
    acquire_capture_lease,
    lease_health,
    release_capture_lease,
)


def test_second_acquire_raises(tmp_path):
    a = acquire_capture_lease("USB3.0 Video", lock_dir=tmp_path)
    assert a.owner == "qoresence-streamer"
    assert a.pid == os.getpid()
    with pytest.raises(CaptureLeaseError):
        acquire_capture_lease("USB3.0 Video", lock_dir=tmp_path)
    release_capture_lease(a)
    b = acquire_capture_lease("USB3.0 Video", lock_dir=tmp_path)
    release_capture_lease(b)


def test_lease_health_ok_and_lost(tmp_path):
    h0 = lease_health(lock_dir=tmp_path, device="USB3.0 Video")
    assert h0["ok"] is False
    a = acquire_capture_lease("USB3.0 Video", lock_dir=tmp_path)
    h = lease_health(lock_dir=tmp_path, device="USB3.0 Video")
    assert h["ok"] is True
    assert h["owner"] == "qoresence-streamer"
    assert h["pid"] == os.getpid()
    release_capture_lease(a)
    h2 = lease_health(lock_dir=tmp_path, device="USB3.0 Video")
    assert h2["ok"] is False


def test_pattern_b_helper_hard_fails_dshow_dual_open():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "tools" / "obs" / "pattern_b_x_live.ps1").read_text(
        encoding="utf-8"
    )
    assert "DUAL_OPEN" in text
    assert "throw" in text.lower() or "Write-Error" in text or "exit 2" in text
    # Warn-only is not the contract.
    assert "WARN: source" not in text or "DUAL_OPEN" in text
