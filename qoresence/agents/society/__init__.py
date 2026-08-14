"""Agent Society — narrow ops agents on the local glass. Default OFF."""

from .config import AgentSocietyConfig
from .runtime import (
    SocietyRuntime,
    get_society,
    run_audit_once,
    run_propose_cuts_once,
    start_society,
    stop_society,
)
from .types import AgentPacket, AgentReceipt

__all__ = [
    "AgentSocietyConfig",
    "AgentPacket",
    "AgentReceipt",
    "SocietyRuntime",
    "start_society",
    "stop_society",
    "get_society",
    "run_audit_once",
    "run_propose_cuts_once",
]
