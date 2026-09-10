"""Clock Notary compose layer — observation envelope + consent-gated wrap."""

from .locks import DualLocks, LockState
from .envelope import ObservationEnvelope, Tick, build_envelope, clock_commitment
from .sanitize import strip_truth_leaks
from .wrap import ConsentRecord, WrapResult, wrap_notary
from .door import SEAL_PHRASE, export_door, seal_door, verify_door

__all__ = [
    "DualLocks",
    "LockState",
    "ObservationEnvelope",
    "Tick",
    "build_envelope",
    "clock_commitment",
    "strip_truth_leaks",
    "ConsentRecord",
    "WrapResult",
    "wrap_notary",
    "SEAL_PHRASE",
    "export_door",
    "seal_door",
    "verify_door",
]

__version__ = "0.1.1"
