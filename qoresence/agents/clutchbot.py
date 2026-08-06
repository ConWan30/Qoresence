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
from .helix_client import TwitchHelixClient
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
        self._helix_client: TwitchHelixClient | None = None

        self._features = self._build_features()
        for backend in self._build_backends():
            self._executor.add_backend(backend)

        self._last_action_time: dict[str, float] = {}
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
            f"features={sorted(self._features)}, "
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
        active_prediction = self._helix_client.active_prediction if self._helix_client else None
        moments = self._scorer.score(
            self._situation.state,
            event_type=event.type.value,
            event_payload=event.payload,
            active_prediction=active_prediction,
            features=self._features,
        )

        if not moments:
            return

        for moment in moments:
            if not self._rate_limit_ok(moment):
                continue

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

            self._last_action_time[moment.action] = time.time()

    def _rate_limit_ok(self, moment: ScoredMoment) -> bool:
        """Enforce action rate limits."""
        now = time.time()

        if moment.action == "chat":
            # Per-minute bucket
            if now - self._minute_start >= 60.0:
                self._minute_start = now
                self._messages_this_minute = 0

            if self._messages_this_minute >= self.config.max_messages_per_min:
                log.debug("ClutchBot hit per-minute message limit")
                return False

            self._messages_this_minute += 1

        # Global cooldown per action type
        last = self._last_action_time.get(moment.action, 0.0)
        cooldown_s = self._cooldown_for(moment.action)
        if now - last < cooldown_s:
            log.debug(f"ClutchBot {moment.action} cooldown active")
            return False

        return True

    @staticmethod
    def _cooldown_for(action: str) -> float:
        if action == "chat":
            return 30.0
        if action == "clip":
            return 60.0
        if action in ("start_prediction", "resolve_prediction"):
            return 5.0
        return 0.0

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

    def _build_features(self) -> set[str]:
        features: set[str] = {"chat"}
        tw = self.config.twitch
        if tw and tw.enabled:
            if tw.enable_clips:
                features.add("clip")
            if tw.enable_predictions:
                features.add("prediction")
        return features

    def _build_backends(self) -> list[Backend]:
        backends: list[Backend] = []
        tw = self.config.twitch
        if not tw or not tw.enabled:
            return backends

        irc_client: TwitchIRCClient | None = None
        if tw.bot_username and (tw.oauth_token or tw.token_file):
            irc_client = TwitchIRCClient(
                username=tw.bot_username,
                oauth_token=self._resolve_irc_token(tw),
                channel=tw.channel,
                min_interval_s=tw.message_interval_s,
            )
            backends.append(_TwitchChatBackend(irc_client))

        if tw.client_id and (tw.broadcaster_id or tw.broadcaster_username):
            helix_token = self._resolve_helix_token(tw)
            self._helix_client = TwitchHelixClient(
                client_id=tw.client_id,
                access_token=helix_token,
                broadcaster_id=tw.broadcaster_id,
                broadcaster_username=tw.broadcaster_username,
            )

            if tw.enable_clips:
                backends.append(_TwitchClipBackend(self._helix_client, irc_client))

            if tw.enable_predictions:
                backends.append(_TwitchPredictionBackend(self._helix_client, irc_client))

        return backends

    @staticmethod
    def _resolve_irc_token(config: TwitchConfig) -> str:
        if config.oauth_token:
            return config.oauth_token
        if config.token_file:
            p = Path(config.token_file)
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        raise ValueError("Twitch OAuth token or token_file required")

    @staticmethod
    def _resolve_helix_token(config: TwitchConfig) -> str:
        if config.helix_token:
            return config.helix_token
        if config.helix_token_file:
            p = Path(config.helix_token_file)
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        # Fallback to IRC token if no Helix-specific token supplied
        return ClutchBotAgent._resolve_irc_token(config)


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


class _TwitchClipBackend:
    """Creates Twitch clips and announces the edit URL in chat."""

    def __init__(self, helix: TwitchHelixClient, irc: TwitchIRCClient | None):
        self.helix = helix
        self.irc = irc

    def name(self) -> str:
        return "twitch_clip"

    def start(self) -> bool:
        return self.helix.start()

    def stop(self) -> None:
        self.helix.stop()

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        if action != "clip":
            return False

        result = self.helix.create_clip()
        if not result:
            return False

        if self.irc:
            message = f"🎬 Clutch clip: {result.edit_url}"
            self.irc.send_message(message)

        return True


class _TwitchPredictionBackend:
    """Starts and resolves Twitch channel-point predictions."""

    def __init__(self, helix: TwitchHelixClient, irc: TwitchIRCClient | None):
        self.helix = helix
        self.irc = irc

    def name(self) -> str:
        return "twitch_prediction"

    def start(self) -> bool:
        return self.helix.start()

    def stop(self) -> None:
        self.helix.stop()

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        if action == "start_prediction":
            title = payload.get("payload", {}).get("title") or payload.get("message", "Will it happen?")
            outcomes = payload.get("payload", {}).get("outcomes") or ["Yes", "No"]
            window_s = payload.get("payload", {}).get("window_s") or 120
            result = self.helix.create_prediction(title, outcomes, window_s)
            if result and self.irc:
                self.irc.send_message(f"📊 Prediction live: {result.title}")
            return result is not None

        if action == "resolve_prediction":
            winning = payload.get("payload", {}).get("winning_outcome_index", 0)
            success = self.helix.resolve_prediction(winning)
            if success and self.irc:
                result = "Yes" if winning == 0 else "No"
                self.irc.send_message(f"📊 Prediction resolved: {result}")
            return success

        return False
