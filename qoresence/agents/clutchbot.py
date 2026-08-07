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
from .eventsub_client import TwitchEventSubClient
from .helix_client import TwitchHelixClient
from .learning_loop import LearningLogger
from .llm_client import LLMConfig, QuicksilverLLMClient
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

        _learning_logger: LearningLogger | None = None
        if getattr(config, "learning_enabled", False):
            try:
                _learning_logger = LearningLogger(path=getattr(config, "learning_log_path", None))
                log.info(
                    f"ClutchBot learning loop enabled -> {_learning_logger.path} (opt-in, frame_hash[:16] only)"
                )
            except Exception as e:
                log.warning(f"LearningLogger init failed: {e}")
                _learning_logger = None
        self._learning_logger: LearningLogger | None = _learning_logger

        self._situation = SituationModel(window_s=config.controller_window_s)
        self._scorer = MomentScorer(persona=config.persona, learning_logger=_learning_logger)
        self._executor = ActionExecutor()
        self._memory = SessionMemory(
            output_path=Path(config.memory_path) if config.memory_path else None
        )
        self._helix_client: TwitchHelixClient | None = None
        # -- LLM via Quicksilver Pro (dedicated API, optional) --
        try:
            _llm_cfg = LLMConfig.from_clutchbot(config)
            self._llm: QuicksilverLLMClient | None = QuicksilverLLMClient(_llm_cfg)
            if _llm_cfg.enabled and self._llm.is_available():
                log.info(
                    f"ClutchBot LLM enabled: {_llm_cfg.provider}/{_llm_cfg.model} @ {_llm_cfg.base_url}"
                )
            elif _llm_cfg.enabled:
                log.warning(
                    "ClutchBot LLM enabled but no API key — template fallback (set .secrets/quicksilver_clutchbot.key)"
                )
            else:
                log.debug("ClutchBot LLM disabled — template mode")
        except Exception as e:
            log.warning(f"LLM init failed: {e}")
            self._llm = None  # type: ignore[attr-defined]

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
            f"backends={[b.name() for b in self._executor.backends]}, "
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

        if getattr(self, "_learning_logger", None) is not None and moments:
            try:
                for _lm in moments:
                    if _lm.triggered:
                        self._learning_logger.log(
                            state=self._situation.to_dict(),
                            moment=_lm,
                            label=None,
                            frame_hash=str(event.payload.get("frame_hash", ""))
                            if isinstance(event.payload, dict)
                            else "",
                            wp_swing=float(_lm.payload.get("wp_swing", 0.0) or 0.0),
                        )
            except Exception as e:
                log.debug(f"LearningLogger log failed: {e}")

        if not moments:
            return

        for moment in moments:
            # LLM via Quicksilver Pro https://api.quicksilverpro.io/v1 (fallback to template)
            _llm = getattr(self, "_llm", None)
            if (
                _llm is not None
                and _llm.is_available()
                and moment.action == "chat"
                and moment.message
            ):
                try:
                    _enh = _llm.enhance_message(
                        situation=self._situation.to_dict(),
                        event_type=event.type.value,
                        event_payload=event.payload if isinstance(event.payload, dict) else None,
                        persona=self.config.persona,
                        base_message=moment.message,
                    )
                    if _enh and len(_enh) > 4:
                        import dataclasses as _dc

                        moment = _dc.replace(moment, message=_enh)
                except Exception as _e:
                    log.debug(f"LLM enhance failed: {_e}")

            if not self._rate_limit_ok(moment):
                continue

            context = {
                "session_id": self.bus.session_id,
                "event_type": event.type.value,
                "event_clock_ns": event.clock_ns,
            }
            results = self._executor.execute(moment, context)

            # Only count chat if it actually reached a backend successfully
            if moment.action == "chat" and any(r.success for r in results):
                self._record_chat_sent()

            self._emit_agent_action(moment, results)
            self._memory.record(
                moment=moment,
                situation=self._situation,
                results=[
                    {
                        "backend": r.backend,
                        "action": r.action,
                        "success": r.success,
                        "detail": r.detail,
                    }
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

        # Global cooldown per action type
        last = self._last_action_time.get(moment.action, 0.0)
        cooldown_s = self._cooldown_for(moment.action)
        if now - last < cooldown_s:
            log.debug(f"ClutchBot {moment.action} cooldown active")
            return False

        return True

    def _record_chat_sent(self) -> None:
        """Increment per-minute chat counter after a successful send."""
        now = time.time()
        if now - self._minute_start >= 60.0:
            self._minute_start = now
            self._messages_this_minute = 0
        self._messages_this_minute += 1

    def _cooldown_for(self, action: str) -> float:
        base = self.config.message_cooldown_s
        if action == "chat":
            return base
        if action == "clip":
            return max(60.0, base)
        if action == "start_prediction":
            return max(120.0, base)
        if action == "resolve_prediction":
            return 5.0
        return max(10.0, base)

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
        features: set[str] = set()
        if self.config.enable_chat:
            features.add("chat")
        # Local HDMI clips always available (capture ring buffer) — not Helix-only
        features.add("clip")
        tw = self.config.twitch
        if tw and tw.enabled:
            if tw.enable_predictions:
                features.add("prediction")
        return features

    def _build_backends(self) -> list[Backend]:
        backends: list[Backend] = []

        # Always wire Deck feed so Rail/Lens clutch feed updates without Twitch.
        # Local HDMI clip buffer (true capture card) for clip actions.
        backends.append(_DeckFeedBackend())
        backends.append(_LocalHdmiClipBackend())

        tw = self.config.twitch
        if not tw or not tw.enabled:
            log.info(
                "ClutchBot backends: deck_feed + local_hdmi "
                "(set --clutchbot-channel + token for Twitch IRC)"
            )
            return backends

        irc_client: TwitchIRCClient | None = None
        if tw.bot_username and (tw.oauth_token or tw.token_file):
            try:
                irc_client = TwitchIRCClient(
                    username=tw.bot_username,
                    oauth_token=self._resolve_irc_token(tw),
                    channel=tw.channel,
                    min_interval_s=tw.message_interval_s,
                    command_callback=self._handle_chat_command,
                )
                backends.append(_TwitchChatBackend(irc_client))
            except Exception as e:
                log.warning("Twitch IRC backend not wired: %s", e)

        if tw.client_id and (tw.broadcaster_id or tw.broadcaster_username):
            try:
                helix_token = self._resolve_helix_token(tw)
                self._helix_client = TwitchHelixClient(
                    client_id=tw.client_id,
                    access_token=helix_token,
                    broadcaster_id=tw.broadcaster_id,
                    broadcaster_username=tw.broadcaster_username,
                )

                if tw.enable_clips:
                    backends.append(
                        _TwitchClipBackend(
                            self._helix_client, irc_client, has_delay=self.config.clip_has_delay
                        )
                    )

                if tw.enable_predictions:
                    backends.append(_TwitchPredictionBackend(self._helix_client, irc_client))

                if tw.enable_follow_alerts or tw.enable_sub_alerts or tw.enable_redemption_alerts:
                    backends.append(_TwitchEventSubBackend(self._helix_client, irc_client, tw))
            except Exception as e:
                log.warning("Twitch Helix backends not wired: %s", e)

        log.info(
            "ClutchBot backends: %s",
            [getattr(b, "name", lambda: "?")() for b in backends],
        )
        return backends

    def _handle_chat_command(self, sender: str, text: str) -> str | None:
        """Respond to viewer chat commands."""
        parts = text.lower().split()
        if not parts:
            return None

        cmd = parts[0]
        if cmd == "!state":
            s = self._situation.state
            return (
                f"Qoresence sees {s.game_title or 'a game'} — "
                f"{s.home_score or '?'} - {s.away_score or '?'} Q{s.quarter or '?'}, "
                f"{s.possession or '?'} ball, {s.down or '?'} & {s.yards_to_go or '?'}."
            )

        if cmd == "!score":
            s = self._situation.state
            return f"Score: {s.home_score or '?'} - {s.away_score or '?'} (Q{s.quarter or '?'})."

        if cmd == "!lastclip":
            if self._helix_client and self._helix_client.last_clip_url:
                return f"Last clutch clip: {self._helix_client.last_clip_url}"
            return "No clutch clip yet."

        if cmd == "!help":
            return "ClutchBot commands: !state, !score, !lastclip, !help"

        return None

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


class _LocalHdmiClipBackend:
    """Export last N seconds from the capture-card ring buffer (true PS5 HDMI)."""

    def name(self) -> str:
        return "local_hdmi"

    def start(self) -> bool:
        try:
            from qoresence.vision.clip_buffer import get_clip_buffer

            get_clip_buffer()  # ensure singleton exists
            log.info("LocalHdmiClip backend ready (clips/hdmi_clip_*.mp4)")
            return True
        except Exception as e:
            log.warning("LocalHdmiClip backend unavailable: %s", e)
            return True  # non-fatal

    def stop(self) -> None:
        return None

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        if action != "clip":
            return False
        try:
            from qoresence.vision.clip_buffer import export_clip
            from qoresence.deck.server import push_moment as _deck_push

            seconds = None
            inner = payload.get("payload") or {}
            if isinstance(inner, dict) and inner.get("seconds") is not None:
                seconds = float(inner["seconds"])
            result = export_clip(seconds=seconds)
            if result is None:
                log.warning("LocalHdmiClip: buffer empty — keep playing to fill ~5–30s")
                _deck_push(
                    {
                        "title": "CLIP failed — buffer empty",
                        "reason": "wait for HDMI frames",
                        "clock": "now",
                        "action": "clip",
                        "icon": "🎬",
                    }
                )
                return False
            from pathlib import Path as _P

            clip_name = _P(result.path).name
            media_url = f"/media/clips/{clip_name}"
            _deck_push(
                {
                    "title": f"HDMI CLIP {result.duration_s:.0f}s",
                    "reason": result.path,
                    "clock": "now",
                    "action": "clip",
                    "icon": "🎬",
                    "path": result.path,
                    "name": clip_name,
                    "url": media_url,
                }
            )
            log.info("LocalHdmiClip saved %s", result.path)
            return True
        except Exception as e:
            log.warning("LocalHdmiClip failed: %s", e)
            return False


class _DeckFeedBackend:
    """Local always-on backend: push scored moments into Retina Deck Rail/Lens.

    No network. Works offline so `Action executor started with 0 backend(s)` never
    happens under --play. Twitch IRC is optional on top.
    """

    def name(self) -> str:
        return "deck_feed"

    def start(self) -> bool:
        log.info("DeckFeed backend ready (moments → /retina + Rail feed)")
        return True

    def stop(self) -> None:
        return None

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        # Clips are owned by local_hdmi (real MP4). DeckFeed still handles chat/etc.
        if action == "clip":
            return False
        title = (
            payload.get("message")
            or (payload.get("payload") or {}).get("title")
            or action
            or "CLUTCH"
        )
        reason = payload.get("reason") or action or ""
        try:
            from qoresence.deck.server import push_moment as _deck_push

            _deck_push(
                {
                    "title": str(title)[:80],
                    "reason": str(reason)[:160],
                    "clock": "now",
                    "action": str(action),
                    "icon": "⚡" if action == "chat" else "📊",
                }
            )
            log.info("DeckFeed %s: %s", action, str(title)[:60])
            return True
        except Exception as e:
            log.warning("DeckFeed push failed: %s", e)
            return False


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
    """Creates Twitch clips and announces the public URL in chat."""

    def __init__(
        self, helix: TwitchHelixClient, irc: TwitchIRCClient | None, has_delay: bool = True
    ):
        self.helix = helix
        self.irc = irc
        self.has_delay = has_delay

    def name(self) -> str:
        return "twitch_clip"

    def start(self) -> bool:
        return self.helix.start()

    def stop(self) -> None:
        self.helix.stop()

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        if action != "clip":
            return False

        result = self.helix.create_clip(has_delay=self.has_delay)
        if not result:
            return False

        if self.irc:
            clip_url = result.url or result.edit_url
            message = f"🎬 Clutch clip: {clip_url}"
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
            inner = payload.get("payload", {})
            title = inner.get("title") or payload.get("message", "Will it happen?")
            outcomes = inner.get("outcomes") or ["Yes", "No"]
            window_s = inner.get("window_s") or 120
            offense = inner.get("offense")
            result = self.helix.create_prediction(title, outcomes, window_s, offense=offense)
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


class _TwitchEventSubBackend:
    """Wraps the EventSub client as an ActionExecutor backend."""

    def __init__(self, helix: TwitchHelixClient, irc: TwitchIRCClient | None, config: TwitchConfig):
        self.client = TwitchEventSubClient(
            helix,
            irc,
            follow_alerts=config.enable_follow_alerts,
            sub_alerts=config.enable_sub_alerts,
            redemption_alerts=config.enable_redemption_alerts,
        )

    def name(self) -> str:
        return "twitch_eventsub"

    def start(self) -> bool:
        return self.client.start()

    def stop(self) -> None:
        self.client.stop()

    def execute(self, action: str, payload: dict[str, Any]) -> bool:
        return False
