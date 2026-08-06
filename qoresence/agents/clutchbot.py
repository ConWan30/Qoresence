"""
ClutchBot — game-state-aware Twitch agent for Qoresence.

Consumes Qoresence bus events, builds a rolling situation model, scores
narrative moments, and dispatches actions (chat messages, clips, predictions)
to pluggable backends.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from qoresence.core import (
    BaseEvent,
    ClutchBotConfig,
    EventType,
    RetinaEventBus,
    SourceLobe,
    TwitchConfig,
    clock_ns,
)

from .action_executor import ActionExecutor, Backend
from .moment_scorer import MomentScorer, ScoredMoment
from .session_memory import SessionMemory
from .situation_model import SituationModel
from .twitch_client import TwitchIRCClient

log = logging.getLogger(__name__)


class ClutchBotAgent:
    """Agentic Twitch companion for Qoresence."""

    def __init__(
        self,
        config: ClutchBotConfig,
        bus: RetinaEventBus,
        session_head_ns: int,
    ):
        self.config = config
        self.bus = bus
        self.session_head_ns = session_head_ns

        self._running = False
        self._unsubscribe: Callable[[], None] | None = None

        self._situation = SituationModel(window_s=config.controller_window_s)
        self._scorer = MomentScorer(persona=config.persona)
        self._executor = ActionExecutor()
        self._memory = SessionMemory(
            output_path=Path(config.memory_path) if config.memory_path else None
        )

        for backend in self._build_backends():
            self._executor.add_backend(backend)

        self._last_action_time = 0.0
        self._messages_this_minute = 0
        self._minute_start = 0.0

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True

        self._running = True

        if not self._executor.start():
            log.error("ClutchBot could not start action backends")
            return False

        self._unsubscribe = self.bus.subscribe(self._on_event)
        self._minute_start = time.time()
        log.info(
            f"ClutchBot started: persona={self.config.persona}, "
            f"max_chat_per_min={self.config.max_messages_per_min}"
        )
        return True

    def stop(self) -> None:
        self._running = False
        if self._unsubscribe:
            try:
                self._unsubscribe()
            except Exception as e:
                log.debug(f"ClutchBot unsubscribe error: {e}")
            self._unsubscribe = None
        self._executor.stop()
        log.info("ClutchBot stopped")

    def is_running(self) -> bool:
        return self._running

    def get_situation(self) -> dict[str, Any]:
        return self._situation.to_dict()

    # ──────────────────────────────────────────────────────────────────────────
    # EVENT HANDLER
    # ──────────────────────────────────────────────────────────────────────────

    def _on_event(self, event: BaseEvent) -> None:
        if not self._running:
            return

        self._situation.update(event)

        if event.type in {
            EventType.VISUAL_CONTEXT,
            EventType.OUTCOME_EVENT,
            EventType.GAME_DETECTED,
            EventType.CONTROLLER_EVENT,
            EventType.TRIGGER_ONSET,
            EventType.STICK_MOTION,
            EventType.PRESENCE_REPORT,
        }:
            self._maybe_act(event)

    def _maybe_act(self, event: BaseEvent) -> None:
        if event.type == EventType.OUTCOME_EVENT:
            moment = self._scorer.score(
                self._situation.state,
                event_type=event.type.value,
                event_payload=event.payload,
            )
        elif event.type == EventType.GAME_DETECTED:
            moment = self._scorer.score(
                self._situation.state,
                event_type=event.type.value,
                event_payload=event.payload,
            )
        else:
            # Visual context can trigger a chat update if score is close/late
            if event.type == EventType.VISUAL_CONTEXT:
                moment = self._scorer.score(
                    self._situation.state,
                    event_type=event.type.value,
                    event_payload=event.payload,
                )
            else:
                return

        if not moment.triggered:
            return

        if not self._rate_limit_ok(moment):
            return

        context = {
            "session_id": self.bus.session_id,
            "event_type": event.type.value,
            "event_clock_ns": event.clock_ns,
        }
        results = self._executor.execute(moment, context)

        self._emit_agent_action(moment, results)
        self._memory.record(
            moment=moment,
            situation=self._situation,
            results=[
                {"backend": r.backend, "action": r.action, "success": r.success, "detail": r.detail}
                for r in results
            ],
        )

        self._last_action_time = time.time()

    def _rate_limit_ok(self, moment: ScoredMoment) -> bool:
        """Enforce message rate limits."""
        if moment.action != "chat":
            return True

        now = time.time()

        # Per-minute bucket
        if now - self._minute_start >= 60.0:
            self._minute_start = now
            self._messages_this_minute = 0

        if self._messages_this_minute >= self.config.max_messages_per_min:
            log.debug("ClutchBot hit per-minute message limit")
            return False

        # Global cooldown
        if now - self._last_action_time < self.config.message_cooldown_s:
            log.debug("ClutchBot global cooldown active")
            return False

        self._messages_this_minute += 1
        return True

    def _emit_agent_action(self, moment: ScoredMoment, results: list[Any]) -> None:
        self.bus.emit_raw(
            source_lobe=SourceLobe.AGENT,
            event_type=EventType.AGENT_ACTION,
            payload={
                "agent_name": "clutchbot",
                "action": moment.action,
                "message": moment.message,
                "weight": moment.weight,
                "reason": moment.reason,
                "backends": [r.backend for r in results],
                "situation": self._situation.to_dict(),
            },
            clock_ns_override=clock_ns(),
            session_head_ns=self.session_head_ns,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # BACKEND FACTORY
    # ──────────────────────────────────────────────────────────────────────────

    def _build_backends(self) -> list[Backend]:
        backends: list[Backend] = []

        if self.config.twitch and self.config.twitch.enabled:
            from .twitch_client import TwitchIRCClient

            client = TwitchIRCClient(
                username=self.config.twitch.bot_username,
                oauth_token=self._resolve_token(self.config.twitch),
                channel=self.config.twitch.channel,
                min_interval_s=self.config.twitch.message_interval_s,
            )
            backends.append(_TwitchChatBackend(client))

        return backends

    @staticmethod
    def _resolve_token(config: TwitchConfig) -> str:
        if config.oauth_token:
            return config.oauth_token
        if config.token_file:
            from pathlib import Path

            p = Path(config.token_file)
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        raise ValueError("Twitch OAuth token or token_file required")


class _TwitchChatBackend:
    """Wraps TwitchIRCClient as an ActionExecutor Backend."""

    def __init__(self, client: TwitchIRCClient):
        self.client = client

    def name(self) -> str:
        return "twitch_irc"

    def start(self) -> bool:
        return self.client.start()

    def stop(self) -> None:
        self.client.stop()

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        if action != "chat":
            return False
        message = payload.get("message", "")
        if not message:
            return False
        return self.client.send_message(message)
