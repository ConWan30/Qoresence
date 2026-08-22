"""A2A orchestrator: event-driven scene → chat → policy → commit.

Triggers are reason-coded (score change, menu exit, drive, coupling, ambient).
Never call from streamer grab thread synchronously.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from qoresence.a2a.bus import A2ABus
from qoresence.a2a.deepseek_agent import DeepSeekChatAgent
from qoresence.a2a.gemini_agent import GeminiSceneAgent
from qoresence.a2a.policy import A2APolicy
from qoresence.a2a.router import (
    build_router_decision,
    evaluate_must_fire,
)
from qoresence.a2a.tools import ToolRegistry, create_default_registry
from qoresence.a2a.types import (
    A2AMessage,
    ChatProposal,
    CommitAct,
    EventRef,
    EvidenceChain,
    FieldProvenance,
    SceneProposal,
    Veto,
)

log = logging.getLogger(__name__)
