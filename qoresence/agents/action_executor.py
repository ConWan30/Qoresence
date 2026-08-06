"""
ActionExecutor for ClutchBot.

Receives scored moments and dispatches them to the configured backends. Phase 1
only supports Twitch IRC chat. The interface is pluggable so Discord, Nostr,
A2A, etc. can be added later without touching the agent core.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from .moment_scorer import ScoredMoment

log = logging.getLogger(__name__)


class Backend(Protocol):
    """Backend that can execute one or more action types."""

    def name(self) -> str: ...
    def start(self) -> bool: ...
    def stop(self) -> None: ...
    def execute(self, action: str, payload: dict[str, Any]) -> bool: ...


@dataclass
class ActionResult:
    """Result of executing an action."""
    backend: str
    action: str
    success: bool
    detail: str


class ActionExecutor:
    """Dispatch scored moments to backends."""

    def __init__(self, backends: list[Backend] | None = None):
        self.backends = backends or []

    def add_backend(self, backend: Backend) -> None:
        self.backends.append(backend)

    def start(self) -> bool:
        for backend in self.backends:
            if not backend.start():
                log.error(f"Backend {backend.name()} failed to start")
                return False
        log.info(f"Action executor started with {len(self.backends)} backend(s)")
        return True

    def stop(self) -> None:
        for backend in self.backends:
            try:
                backend.stop()
            except Exception as e:
                log.warning(f"Backend {backend.name()} stop error: {e}")

    def execute(self, moment: ScoredMoment, context: dict[str, Any] | None = None) -> list[ActionResult]:
        """Execute a scored moment across all backends that can handle it."""
        if not moment.triggered:
            return []

        context = context or {}
        payload = {
            "action": moment.action,
            "message": moment.message,
            "weight": moment.weight,
            "reason": moment.reason,
            "cooldown_key": moment.cooldown_key,
            "payload": moment.payload,
            "context": context,
        }

        results: list[ActionResult] = []
        for backend in self.backends:
            try:
                success = backend.execute(moment.action, payload)
                results.append(ActionResult(
                    backend=backend.name(),
                    action=moment.action,
                    success=success,
                    detail="ok" if success else "backend refused",
                ))
            except Exception as e:
                log.error(f"ActionExecutor error in {backend.name()}: {e}")
                results.append(ActionResult(
                    backend=backend.name(),
                    action=moment.action,
                    success=False,
                    detail=str(e),
                ))

        return results
