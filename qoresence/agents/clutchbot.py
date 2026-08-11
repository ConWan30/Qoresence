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
from typing import Any  # noqa: F401 used by A2A / backends

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
from .fast_moment import FastMomentEngine
from .helix_client import TwitchHelixClient
from .learning_loop import LearningLogger
from .llm_client import LLMConfig, QuicksilverLLMClient
from .moment_scorer import MomentScorer, ScoredMoment
from .prediction_lifecycle import PredictionLifecycleManager, get_prediction_lifecycle
from .session_memory import SessionMemory
from .situation_model import SituationModel
from .twitch_client import TwitchIRCClient

# Optional A2A (Gemini scene ↔ DeepSeek chat)
try:
    from qoresence.a2a.orchestrator import A2AOrchestrator, get_a2a_orchestrator
except Exception:  # pragma: no cover
    A2AOrchestrator = None  # type: ignore
    get_a2a_orchestrator = None  # type: ignore

log = logging.getLogger(__name__)

# Events that can wake the realtime (fast) path — no OCR required
_FAST_TRIGGER_TYPES = frozenset(
    {
        EventType.CONTROLLER_EVENT,
        EventType.TRIGGER_ONSET,
        EventType.STICK_MOTION,
        EventType.COUPLING_SCORE,
        EventType.PRESENCE_REPORT,
        EventType.VISUAL_CONTEXT,  # re-score fast with refreshed situation context
    }
)

# Events that drive OCR/outcome confirm path
_CONFIRM_TRIGGER_TYPES = frozenset(
    {
        EventType.VISUAL_CONTEXT,
        EventType.OUTCOME_EVENT,
        EventType.GAME_DETECTED,
    }
)


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
        # Two-speed: fast = video+input co-occurrence; confirm = OCR/outcome referee
        self._fast = FastMomentEngine()
        self._pred_life: PredictionLifecycleManager = get_prediction_lifecycle()
        self._a2a: Any = None
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
        # Wire Helix open/resolve into prediction lifecycle when available
        try:
            self._wire_prediction_lifecycle()
        except Exception as e:
            log.debug("prediction lifecycle wire skipped: %s", e)
        # Optional A2A bus (Gemini ↔ DeepSeek) — sparse, background only
        try:
            self._wire_a2a()
        except Exception as e:
            log.debug("A2A wire skipped: %s", e)
        log.info(
            "ClutchBot started: persona=%s features=%s backends=%s max_chat_per_min=%s "
            "two_speed=fast+confirm a2a=%s (OCR is referee, not starter)",
            self.config.persona,
            sorted(self._features),
            [b.name() for b in self._executor.backends],
            self.config.max_messages_per_min,
            bool(self._a2a and getattr(self._a2a, "enabled", False)),
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

        # Two-speed ClutchBot:
        # 1) Fast path — video+input co-occurrence (IVC), last-known situation
        # 2) Confirm path — OCR/outcome MomentScorer (factual referee)
        if event.type in _FAST_TRIGGER_TYPES:
            try:
                self._maybe_act_fast(event)
            except Exception as e:
                log.debug("ClutchBot fast path error: %s", e)

        if event.type in _CONFIRM_TRIGGER_TYPES or event.type in {
            EventType.CONTROLLER_EVENT,
            EventType.TRIGGER_ONSET,
            EventType.STICK_MOTION,
            EventType.PRESENCE_REPORT,
        }:
            # Confirm still runs on visual/outcome; controller events keep prior
            # behavior for scorer hooks that use APM etc. via situation only when
            # confirm types fire — avoid double-scoring confirm on pure HID.
            if event.type in _CONFIRM_TRIGGER_TYPES:
                self._maybe_act_confirm(event)
                # Event-driven A2A (score / menu exit / sparse scene) — not every visual tick
                if event.type in (EventType.VISUAL_CONTEXT, EventType.OUTCOME_EVENT):
                    try:
                        self._maybe_a2a_from_situation(event=event, coupling=0.0)
                    except Exception as e:
                        log.debug("A2A visual trigger: %s", e)

    def _maybe_act_fast(self, event: BaseEvent) -> None:
        """Realtime path: coupling + last situation → soft chat / clip intent / arm."""
        coupling = None
        if event.type == EventType.COUPLING_SCORE and isinstance(event.payload, dict):
            coupling = event.payload
        else:
            try:
                from qoresence.sync.ivc import get_last_coupling

                coupling = get_last_coupling()
            except Exception:
                coupling = {"coupling": 0.0, "input_energy": 0.0, "path": "fast"}

        # Lifecycle tick (arm TTL / pressure) on every fast-path pulse
        try:
            cval = float((coupling or {}).get("coupling") or 0.0)
            pressure = self._still_pressure_context()
            self._pred_life.tick(coupling=cval, still_pressure_context=pressure, clock_ns=event.clock_ns)
            if (
                "prediction" in self._features
                and self._pred_life.state.value == "armed"
                and cval >= self._pred_life.min_coupling_to_open
            ):
                # Policy open: prefer armed/pressure + climax threshold (DriveGraph)
                allow_open = True
                try:
                    from qoresence.agents.drive_graph import active_drive_graph

                    g = active_drive_graph()
                    if g is not None and g.nodes:
                        ph = g.phase()
                        cl = g.climax_score()
                        allow_open = ph in ("armed", "pressure", "open", "active") and float(
                            cl.get("score") or 0
                        ) >= 0.25
                except Exception:
                    allow_open = True
                if allow_open:
                    self._pred_life.try_open(coupling=cval, clock_ns=event.clock_ns)
            # Sparse A2A on drive pressure / high coupling (never on grab thread await)
            self._maybe_a2a_from_situation(event=event, coupling=cval)
        except Exception as e:
            log.debug("pred lifecycle tick: %s", e)

        moments = self._fast.score_fast(
            self._situation.state,
            coupling=coupling,
            features=self._features,
        )
        if not moments:
            return
        self._dispatch_moments(moments, event, path_label="fast")

    def _maybe_act_confirm(self, event: BaseEvent) -> None:
        """OCR/outcome referee path — may invent nothing; uses real scores when present."""
        active_prediction = self._helix_client.active_prediction if self._helix_client else None
        moments = self._scorer.score(
            self._situation.state,
            event_type=event.type.value,
            event_payload=event.payload,
            active_prediction=active_prediction,
            features=self._features,
        )

        # Confirm score_changed → lifecycle resolve + clear fast latch
        if event.type == EventType.OUTCOME_EVENT and isinstance(event.payload, dict):
            if event.payload.get("event_name") == "score_changed":
                self._fast.on_confirm_score()
                try:
                    win = 0
                    # Heuristic: home increased → Yes(0) often "they scored" if home possession
                    self._pred_life.resolve(
                        int(win),
                        clock_ns=event.clock_ns,
                        reason="OCR score_changed",
                    )
                except Exception as e:
                    log.debug("pred lifecycle resolve: %s", e)
                # Best-effort graph calibration sample on drive close / score resolve
                self._log_drive_graph_sample(event)

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
        self._dispatch_moments(moments, event, path_label="confirm")

    def _dispatch_moments(
        self, moments: list[ScoredMoment], event: BaseEvent, *, path_label: str
    ) -> None:
        for moment in moments:
            if not moment.triggered:
                continue

            # Fast soft chat: never LLM-invent score digits; skip enhance for non-factual
            allow_llm = moment.action == "chat" and moment.message
            if path_label == "fast" or moment.payload.get("factual") is False:
                allow_llm = False  # keep soft templates clean

            _llm = getattr(self, "_llm", None)
            if allow_llm and _llm is not None and _llm.is_available():
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

            # arm_prediction → PredictionLifecycleManager (source of truth for TTL)
            if moment.action == "arm_prediction":
                if not self._rate_limit_ok(moment):
                    continue
                pl = moment.payload if isinstance(moment.payload, dict) else {}
                try:
                    self._pred_life.arm(
                        coupling=pl.get("coupling"),
                        frame_seq=pl.get("frame_seq"),
                        buttons=list(pl.get("buttons") or []),
                        reason=moment.reason or "fast arm_prediction",
                        clock_ns=event.clock_ns,
                        auto_open=False,  # never open Helix on every arm
                    )
                    self._fast._prediction_armed = True  # keep FastMoment latch in sync
                except Exception as e:
                    log.debug("pred arm failed: %s", e)
                context = {
                    "session_id": self.bus.session_id,
                    "event_type": event.type.value,
                    "event_clock_ns": event.clock_ns,
                    "path": path_label,
                }
                results = self._executor.execute(moment, context)
                self._emit_agent_action(moment, results)
                # Timeline already got kind=arm from lifecycle; skip double arm row
                # but record fast_chat-style heat if needed — arm is enough
                self._last_action_time[moment.action] = time.time()
                continue

            if not self._rate_limit_ok(moment):
                continue

            context = {
                "session_id": self.bus.session_id,
                "event_type": event.type.value,
                "event_clock_ns": event.clock_ns,
                "path": path_label,
            }
            results = self._executor.execute(moment, context)

            if moment.action == "chat" and any(r.success for r in results):
                self._record_chat_sent()
                # Remember text for duplicate suppress
                try:
                    msg = (moment.message or "").strip().lower()
                    msg = " ".join(msg.split())[:120]
                    if msg:
                        if not hasattr(self, "_recent_chat_texts"):
                            self._recent_chat_texts = {}
                        self._recent_chat_texts[msg] = time.time()
                except Exception:
                    pass

            # Lifecycle mirrors MomentScorer prediction actions when they fire
            if moment.action == "start_prediction":
                try:
                    pl = moment.payload if isinstance(moment.payload, dict) else {}
                    if self._pred_life.state.value == "idle":
                        self._pred_life.arm(
                            coupling=pl.get("coupling"),
                            reason="confirm start_prediction",
                            clock_ns=event.clock_ns,
                        )
                    self._pred_life.try_open(
                        coupling=pl.get("coupling"),
                        force=True,
                        title=moment.message or "Will they score?",
                        clock_ns=event.clock_ns,
                    )
                except Exception as e:
                    log.debug("pred open from scorer: %s", e)
            if moment.action == "resolve_prediction":
                try:
                    pl = moment.payload if isinstance(moment.payload, dict) else {}
                    win = int(pl.get("winning_outcome_index", 0) or 0)
                    self._pred_life.resolve(win, clock_ns=event.clock_ns, reason=moment.reason or "resolve")
                    self._fast.on_confirm_score()
                except Exception as e:
                    log.debug("pred resolve from scorer: %s", e)

            self._emit_agent_action(moment, results)
            self._record_timeline(moment, path_label=path_label, event=event)
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

    def _still_pressure_context(self) -> bool:
        """True if situation still looks like a clutch window (red zone / close / late)."""
        try:
            st = self._situation.state
            from qoresence.agents.fast_moment import FastMomentEngine

            return bool(
                FastMomentEngine._is_red_zone(st)
                or (FastMomentEngine._is_close(st) and FastMomentEngine._is_late(st))
            )
        except Exception:
            return True

    def _wire_a2a(self) -> None:
        """Enable Gemini↔DeepSeek A2A when QORESENCE_A2A / config says so."""
        import os

        from qoresence.a2a.orchestrator import get_a2a_orchestrator

        env_on = os.environ.get("QORESENCE_A2A", "0").strip() in {"1", "true", "yes"}
        cfg_on = bool(getattr(self.config, "a2a_enabled", False))
        if not (env_on or cfg_on):
            self._a2a = None
            return

        def _on_commit(act) -> None:
            # Map CommitAct → ScoredMoment-like dispatch on chat path
            try:
                from qoresence.agents.moment_scorer import ScoredMoment

                raw_text = getattr(act, "text", None)
                if isinstance(raw_text, dict):
                    raw_text = raw_text.get("text") or raw_text.get("message") or ""
                text = str(raw_text or "").strip()[:140]
                if not text:
                    return
                moment = ScoredMoment(
                    triggered=True,
                    weight=0.55,
                    action=str(getattr(act, "action", "chat") or "chat"),
                    message=text,
                    reason=str(getattr(act, "reason", "a2a_commit")),
                    cooldown_key="a2a_chat",
                    payload={
                        "path": getattr(act, "path", "fast"),
                        "factual": bool(getattr(act, "factual", False)),
                        "source": "a2a",
                        **(getattr(act, "payload", None) or {}),
                    },
                )
                # Minimal synthetic event for dispatch
                class _E:
                    type = type("T", (), {"value": "a2a_commit"})()
                    clock_ns = clock_ns()
                    payload = {}

                self._dispatch_moments([moment], _E(), path_label=str(moment.payload.get("path") or "fast"))
            except Exception as e:
                log.warning("A2A commit dispatch failed: %s", e)

        # Pass JSONL path so query-memory tool can access the event log
        _jsonl = str(self.bus.jsonl_path) if getattr(self.bus, "jsonl_path", None) else None

        self._a2a = get_a2a_orchestrator(
            enabled=True,
            on_commit=_on_commit,
            persona=str(self.config.persona or "neutral"),
            jsonl_path=_jsonl,
        )
        try:
            self._a2a.bus.set_retina_mirror(self.bus, session_id=self.bus.session_id)
        except Exception:
            pass
        log.info(
            "A2A enabled (gemini_live=%s deepseek_live=%s)",
            self._a2a.gemini.live,
            self._a2a.deepseek.live,
        )

    def _maybe_a2a_from_situation(self, *, event: BaseEvent, coupling: float = 0.0) -> None:
        """Event-driven A2A: score change, menu→gameplay, drive, coupling, rare ambient."""
        if not self._a2a or not getattr(self._a2a, "enabled", False):
            return
        try:
            sit = self._situation.to_dict()
            st = self._situation.state
            prev = getattr(self, "_a2a_prev_snap", None) or {}
            hs, aws = st.home_score, st.away_score
            gst = str(getattr(st.game_state, "value", st.game_state) or "")
            prev_hs, prev_aws = prev.get("home_score"), prev.get("away_score")
            prev_gst = str(prev.get("game_state") or "")

            reason: str | None = None
            # 1) Scoreboard truth changed (OCR/VLM) — highest priority soft react
            if (
                hs is not None
                and aws is not None
                and prev_hs is not None
                and prev_aws is not None
                and (hs, aws) != (prev_hs, prev_aws)
            ):
                reason = "score_changed"
            # 2) Menu/hub → gameplay
            elif prev_gst.lower() in {"menu", "lobby", "hub", "paused"} and gst.lower() in {
                "gameplay",
                "playing",
                "in_game",
            }:
                reason = "menu_exit"
            else:
                phase = None
                try:
                    from qoresence.agents.drive_graph import active_drive_graph

                    g = active_drive_graph()
                    if g is not None:
                        phase = g.phase()
                except Exception:
                    phase = None
                if phase in {"pressure", "armed", "open", "active"}:
                    reason = "drive_pressure"
                elif coupling >= 0.45:
                    reason = "coupling"
                elif gst.lower() in {"gameplay", "playing", "in_game"}:
                    # Sparse scene tick (~45s) with image — not every visual event
                    reason = "scene_tick"
                # else: menu / unknown → no A2A

            self._a2a_prev_snap = {
                "home_score": hs,
                "away_score": aws,
                "game_state": gst,
            }
            if reason is None:
                return

            # Force scoreboard VLM on board-relevant events
            if reason in {"score_changed", "menu_exit"}:
                try:
                    from qoresence.monitor.frame_hub import get_latest
                    from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

                    fr = get_latest()
                    if fr is not None:
                        get_scoreboard_vlm().schedule(
                            fr, force=True, reason=reason, game_state=gst
                        )
                except Exception:
                    pass

            phase = None
            try:
                from qoresence.agents.drive_graph import active_drive_graph

                g = active_drive_graph()
                if g is not None:
                    phase = g.phase()
            except Exception:
                phase = None
            frame_seq = None
            try:
                from qoresence.monitor.frame_hub import get_latest_stamp

                stamp = get_latest_stamp()
                if stamp.get("has_frame"):
                    frame_seq = stamp.get("seq")
            except Exception:
                pass
            jpeg = None
            # Attach JPEG for scene on meaningful reasons (not pure coupling spam)
            if reason in {"score_changed", "menu_exit", "drive_pressure", "scene_tick"}:
                try:
                    from qoresence.vision.clip_buffer import get_latest_jpeg

                    jpeg = get_latest_jpeg()
                except Exception:
                    jpeg = None

            self._a2a.maybe_trigger_from_drive(
                situation=sit,
                coupling=coupling,
                drive_phase=phase,
                frame_seq=frame_seq,
                jpeg_bytes=jpeg,
                path="fast" if reason != "score_changed" else "fast",
                reason=reason,
            )
        except Exception as e:
            log.debug("A2A trigger skipped: %s", e)

    def _log_drive_graph_sample(self, event: BaseEvent) -> None:
        """Thin calibration: match_rate / climax / phase → learning log (non-blocking)."""
        if getattr(self, "_learning_logger", None) is None:
            return
        try:
            from qoresence.agents.drive_graph import active_drive_graph

            g = active_drive_graph()
            if g is None or not g.nodes:
                return
            cl = g.climax_score()
            sample_moment = type(
                "M",
                (),
                {
                    "to_dict": lambda self: {
                        "action": "drive_graph_sample",
                        "path": "system",
                        "phase": g.phase(),
                        "match_rate": cl.get("match_rate"),
                        "climax_score": cl.get("score"),
                        "has_fast_confirm": cl.get("has_fast_confirm"),
                        "drive_id": g.drive_id,
                    }
                },
            )()
            self._learning_logger.log(
                state=self._situation.to_dict(),
                moment=sample_moment,
                label=None,
                frame_hash="",
                wp_swing=float(cl.get("score") or 0.0),
            )
        except Exception as e:
            log.debug("drive graph learning sample skipped: %s", e)

    def _wire_prediction_lifecycle(self) -> None:
        """Optional Helix callbacks — local open if no helix."""
        helix = self._helix_client
        if helix is None:
            return

        def _open(meta: dict[str, Any]) -> bool:
            try:
                title = str(meta.get("title") or "Will they score on this drive?")
                outcomes = meta.get("outcomes") or ["Yes", "No"]
                # Helix client API may vary — best-effort
                if hasattr(helix, "create_prediction"):
                    r = helix.create_prediction(title, outcomes, 60, offense=None)
                    return bool(r)
                return False
            except Exception as e:
                log.debug("helix open failed: %s", e)
                return False

        def _resolve(idx: int) -> bool:
            try:
                if hasattr(helix, "resolve_prediction"):
                    return bool(helix.resolve_prediction(idx))
                return False
            except Exception as e:
                log.debug("helix resolve failed: %s", e)
                return False

        self._pred_life.open_callback = _open
        self._pred_life.resolve_callback = _resolve

    def _record_timeline(
        self, moment: ScoredMoment, *, path_label: str, event: BaseEvent
    ) -> None:
        """Append executed moment to SessionTimeline (shared causal log)."""
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            pl = moment.payload if isinstance(moment.payload, dict) else {}
            path = str(pl.get("path") or path_label or "")
            factual = pl.get("factual")
            if factual is None:
                factual = path == "confirm"
            kind = str(moment.action or "moment")
            if path == "fast":
                kind = {
                    "chat": "fast_chat",
                    "clip": "fast_clip",
                    "arm_prediction": "arm",
                }.get(moment.action, f"fast_{moment.action}")
            elif path == "confirm":
                kind = {
                    "chat": "confirm_chat",
                    "clip": "confirm_clip",
                    "start_prediction": "prediction_open",
                    "resolve_prediction": "prediction_resolve",
                }.get(moment.action, f"confirm_{moment.action}")

            open_drive = moment.action in ("arm_prediction",) or (
                path == "fast" and moment.action in ("chat", "clip") and pl.get("coupling", 0)
            )
            # Open drive on arm or first fast heat; close on resolve / score confirm
            close_drive = moment.action == "resolve_prediction" or (
                path == "confirm"
                and moment.action == "chat"
                and "score" in (moment.reason or "").lower()
            )
            get_session_timeline().append(
                kind=kind,
                path=path,
                message=moment.message or "",
                reason=moment.reason or "",
                frame_seq=pl.get("frame_seq"),
                coupling=pl.get("coupling"),
                buttons=list(pl.get("buttons") or [])[:8],
                factual=bool(factual) if factual is not None else None,
                payload={"action": moment.action, "weight": moment.weight, **{k: v for k, v in pl.items() if k not in ("buttons",)}},
                clock_ns=getattr(event, "clock_ns", None),
                open_drive=bool(open_drive and kind in ("arm", "fast_chat", "fast_clip")),
                close_drive=bool(close_drive),
            )
        except Exception as e:
            log.debug("timeline append skipped: %s", e)

    def _rate_limit_ok(self, moment: ScoredMoment) -> bool:
        """Enforce action rate limits + identical-chat suppress."""
        now = time.time()

        if moment.action == "chat":
            # Per-minute bucket
            if now - self._minute_start >= 60.0:
                self._minute_start = now
                self._messages_this_minute = 0

            if self._messages_this_minute >= self.config.max_messages_per_min:
                log.debug("ClutchBot hit per-minute message limit")
                return False

            # Identical (or near-identical) chat text — do not re-spam feed
            msg = (moment.message or "").strip().lower()
            msg = " ".join(msg.split())[:120]
            if msg:
                if not hasattr(self, "_recent_chat_texts"):
                    self._recent_chat_texts: dict[str, float] = {}
                # prune
                self._recent_chat_texts = {
                    k: t for k, t in self._recent_chat_texts.items() if now - t < 180.0
                }
                last_same = self._recent_chat_texts.get(msg, 0.0)
                if now - last_same < 120.0:
                    log.debug("ClutchBot suppress duplicate chat: %s", msg[:50])
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
        if action == "arm_prediction":
            return 60.0
        if action == "chat":
            return max(base, 45.0)  # never chat faster than 45s for feed hygiene
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
            from qoresence.deck.server import push_moment as _deck_push
            from qoresence.vision.clip_buffer import export_clip

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
            buttons_summary: dict = {}
            try:
                from qoresence.vision.clip_buffer import buttons_summary_for_export

                buttons_summary = buttons_summary_for_export(
                    duration_s=float(result.duration_s or 5.0)
                )
            except Exception:
                buttons_summary = {}
            path_tag = ""
            if isinstance(inner, dict):
                path_tag = str(inner.get("path") or "")
            title = f"HDMI CLIP {result.duration_s:.0f}s"
            if path_tag == "fast":
                title = f"FAST {title}"
            moment_payload = {
                "title": title,
                "reason": result.path,
                "clock": "now",
                "action": "clip",
                "icon": "🎬",
                "path": result.path,
                "name": clip_name,
                "url": media_url,
            }
            if path_tag:
                moment_payload["moment_path"] = path_tag
            if buttons_summary:
                moment_payload["buttons_summary"] = buttons_summary
            _deck_push(moment_payload)
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
        inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        path = (inner or {}).get("path") or payload.get("path") or ""
        factual = (inner or {}).get("factual")
        title = (
            payload.get("message")
            or (inner or {}).get("title")
            or action
            or "CLUTCH"
        )
        reason = payload.get("reason") or action or ""
        if path:
            reason = f"[{path}] {reason}"
        try:
            from qoresence.deck.server import push_moment as _deck_push

            icon = "⚡" if action == "chat" else "📊"
            if path == "fast":
                icon = "⚡" if action == "chat" else ("🎬" if action == "clip" else "🎯")
            if action == "arm_prediction":
                title = title if title and title != "arm_prediction" else "FAST arm prediction"
                icon = "🎯"
            moment = {
                "title": str(title)[:80] if title else str(action),
                "reason": str(reason)[:160],
                "clock": "now",
                "action": str(action),
                "icon": icon,
            }
            if path:
                moment["path"] = path
            if factual is not None:
                moment["factual"] = factual
            _deck_push(moment)
            log.info("DeckFeed %s path=%s: %s", action, path or "—", str(title)[:60])
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
