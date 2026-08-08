"""A2A bus — Gemini scene ↔ DeepSeek chat → ClutchBot (optional).

Sparse agent negotiation under local policy. Does not replace LocalVLM/OCR.
"""

from qoresence.a2a.orchestrator import A2AOrchestrator, get_a2a_orchestrator
from qoresence.a2a.types import (
    A2AMessage,
    ChatProposal,
    CommitAct,
    NeedLook,
    SceneProposal,
    Veto,
)

__all__ = [
    "A2AMessage",
    "A2AOrchestrator",
    "ChatProposal",
    "CommitAct",
    "NeedLook",
    "SceneProposal",
    "Veto",
    "get_a2a_orchestrator",
]
