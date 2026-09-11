"""Clock Notary compose layer — observation envelope + consent-gated wrap."""

from .door import export_door
from .envelope import ObservationEnvelope, Tick, build_envelope, clock_commitment
from .io_ledger import canonicalize_out_edge, out_edge_from_event
from .locks import DualLocks, LockState
from .sanitize import strip_truth_leaks
from .wrap import ConsentRecord, WrapResult, wrap_notary

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
    "export_door",
    "canonicalize_out_edge",
    "out_edge_from_event",
]

__version__ = "0.2.0"
