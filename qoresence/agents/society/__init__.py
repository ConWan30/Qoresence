"""Agent Society — leftover opt-in stub. Default OFF. Actuators, not coworkers."""

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
from .judgment_ledger import (
    PACKS as JUDGMENT_PACKS,
    compose_soft_act,
    ledger_stats,
    note_judgment,
    note_pack_verdict,
)

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
    "JUDGMENT_PACKS",
    "compose_soft_act",
    "ledger_stats",
    "note_judgment",
    "note_pack_verdict",
]
