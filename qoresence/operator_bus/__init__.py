"""Operator-bot RCP mailbox. Not A2ABus. Not Agent Society. Enqueue-only."""

from qoresence.operator_bus.envelope import OperatorEnvelope, parse_envelope
from qoresence.operator_bus.mailbox import (
    OperatorMailbox,
    get_operator_mailbox,
    reset_operator_mailbox,
)
from qoresence.operator_bus.prompt import QOECTOR_BUS_PROMPT, QOREDEV_BUS_PROMPT
from qoresence.operator_bus.qoredev import sequence_from_snapshot

__all__ = [
    "OperatorEnvelope",
    "OperatorMailbox",
    "QOECTOR_BUS_PROMPT",
    "QOREDEV_BUS_PROMPT",
    "get_operator_mailbox",
    "parse_envelope",
    "reset_operator_mailbox",
    "sequence_from_snapshot",
]
