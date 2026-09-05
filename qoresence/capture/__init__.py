"""Capture-card lease — one DShow owner."""

from qoresence.capture.lease import (
    CaptureLease,
    CaptureLeaseError,
    acquire_capture_lease,
    lease_health,
    release_capture_lease,
)

__all__ = [
    "CaptureLease",
    "CaptureLeaseError",
    "acquire_capture_lease",
    "lease_health",
    "release_capture_lease",
]
