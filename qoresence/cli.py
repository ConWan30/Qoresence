"""
Qoresence CLI â€” Phase 9 Production Entry Point

Unified command-line interface for running Qoresence lobes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
import time
from pathlib import Path

# Held open so a second --play cannot race before Deck binds
_PILOT_LOCK_SOCK: socket.socket | None = None


def _run_audit(jsonl_path: str, n: int = 10) -> None:
    """Print the last N evidence chains and router decisions from the JSONL log.

    This is the offline audit view for Trio P4 (evidence chains) and P2
    (router decisions). It reads the JSONL event log and prints a
    human-readable summary of recent A2A decisions.
    """
    import json

    p = Path(jsonl_path)
    if not p.exists():
        print(f"Audit: log not found: {jsonl_path}")  # noqa: T201
        return

    lines = p.read_text(encoding="utf-8").strip().splitlines()
    evidence_chains: list[dict] = []
    router_decisions: list[dict] = []

    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        et = ev.get("type", "")
        if et == "evidence_chain" and len(evidence_chains) < n:
            evidence_chains.append(ev.get("payload") or {})
        elif et == "router_decision" and len(router_decisions) < n * 2:
            router_decisions.append(ev.get("payload") or {})
        if len(evidence_chains) >= n and len(router_decisions) >= n * 2:
            break

    # Print evidence chains
    if not evidence_chains and not router_decisions:
        print("Audit: no evidence_chain or router_decision events found.")  # noqa: T201
        return

    print(f"\n{'=' * 80}")  # noqa: T201
    print(f"AUDIT: {jsonl_path}")  # noqa: T201
    print(f"{'=' * 80}\n")  # noqa: T201

    if evidence_chains:
        print(f"EVIDENCE CHAINS (last {len(evidence_chains)}):")  # noqa: T201
        print("-" * 80)  # noqa: T201
        for i, ec in enumerate(evidence_chains):
            reason = ec.get("trigger_reason", "—")
            conf = ec.get("confidence", 0.0)
            drive = ec.get("drive_phase", "—")
            coup = ec.get("coupling_score", "—")
            scene_model = ec.get("scene_model", "—")
            chat_model = ec.get("chat_model", "—")
            events = [
                e.get("event_name") or e.get("event_type")
                for e in (ec.get("cited_events") or [])
                if e
            ]
            fields = [
                f"{f.get('field_name')}:{f.get('value')}" for f in (ec.get("cited_fields") or [])
            ]
            policy = ec.get("policy_refs") or []

            print(  # noqa: T201
                f"\n  [{i + 1}] reason={reason}  confidence={conf}  drive={drive}  coupling={coup}"
            )
            print(f"      scene_model={scene_model}  chat_model={chat_model}")  # noqa: T201
            if events:
                print(f"      cited_events: {', '.join(events)}")  # noqa: T201
            if fields:
                print(f"      cited_fields: {', '.join(fields[:8])}")  # noqa: T201
            if policy:
                print(f"      policy_refs: {', '.join(policy)}")  # noqa: T201

    if router_decisions:
        print(f"\n\nROUTER DECISIONS (last {len(router_decisions)}):")  # noqa: T201
        print("-" * 80)  # noqa: T201
        fired = sum(1 for r in router_decisions if r.get("fired"))
        suppressed = len(router_decisions) - fired
        print(f"  Total: {len(router_decisions)}  Fired: {fired}  Suppressed: {suppressed}\n")  # noqa: T201
        for i, r in enumerate(router_decisions[:n]):
            fired_str = "FIRED" if r.get("fired") else "SUPP"
            reason = r.get("reason", "—")
            mf = r.get("must_fire_hit")
            mf_str = f" [must-fire:{mf}]" if mf else ""
            interval = r.get("interval_s", 0.0)
            age = r.get("last_trigger_age_s", 0.0)
            print(  # noqa: T201
                f"  [{i + 1:3d}] {fired_str:5s}  reason={reason:20s}  interval={interval:.1f}s  age={age:.1f}s{mf_str}"
            )

    print(f"\n{'=' * 80}\n")  # noqa: T201


def _acquire_pilot_lock(port: int = 8765) -> bool:
    """Prevent dual --play/--deck processes (second open freezes DShow card).

    Binds an exclusive probe socket on port+10000 (e.g. 18765) for process life,
    and refuses if Deck port is already listening.
    """
    global _PILOT_LOCK_SOCK
    try:
        # If Deck already serving, refuse
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.settimeout(0.4)
        try:
            probe.connect(("127.0.0.1", int(port)))
            probe.close()
            return False  # something is listening on deck port
        except OSError:
            probe.close()

        # Exclusive lock socket (survives until process exit)
        lock_port = int(port) + 10000
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Windows: exclusive bind without reuse
            sock.bind(("127.0.0.1", lock_port))
            sock.listen(1)
        except OSError:
            sock.close()
            return False
        _PILOT_LOCK_SOCK = sock
        lock = Path("logs") / "qoresence_play.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(f"{os.getpid()} deck={port} lock={lock_port}\n", encoding="utf-8")
        return True
    except Exception:
        return True  # never hard-block on lock IO errors


from qoresence.agents import ClutchBotAgent  # noqa: E402
from qoresence.core import (  # noqa: E402
    RetinaEventBus,
    RetinaUnifiedConfig,
    SessionAuthority,
    TwitchConfig,
    clock_ns,
)
from qoresence.fusion import PresenceFusionEngine, create_fusion_engine  # noqa: E402
from qoresence.game_detection import GameAutoDetector  # noqa: E402

try:
    from qoresence.deck.server import DECK_HOST as _DECK_HOST  # noqa: E402
    from qoresence.deck.server import DECK_PORT as _DECK_PORT  # noqa: E402
    from qoresence.deck.server import start_deck as _start_deck  # noqa: E402

    _DECK_AVAILABLE = True
except ImportError:
    _start_deck = None  # type: ignore[assignment]
    _DECK_HOST = "127.0.0.1"
    _DECK_PORT = 8765
    _DECK_AVAILABLE = False
from qoresence.lobes import (  # noqa: E402
    ControllerRuntime,
    OutcomeRuntime,
    ScreenRuntime,
    StreamerRuntime,
    VisualRuntime,
)

# Optional trio-retina
try:
    from qoresence.trio import TrioRetinaConfig

    TRIO_AVAILABLE = True
except ImportError:
    TRIO_AVAILABLE = False
    TrioRetinaConfig = None  # type: ignore

log = logging.getLogger(__name__)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# GLOBAL STATE
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


class QoresenceApp:
    """Main application coordinator."""

    def __init__(self, config: RetinaUnifiedConfig, trio_config: TrioRetinaConfig | None = None):
        self.config = config
        self.trio_config = trio_config
        self.identity = SessionAuthority.mint(
            session_id=config.session_id,
            device_id_hex=config.device_id_hex,
            session_head_ns=config.session_head_ns,
        )

        # Event bus with trio-retina validation
        self.streamr_publisher = None
        if config.streamr.enabled:
            from qoresence.streamr.publisher import make_streamr_publisher_from_config

            self.streamr_publisher = make_streamr_publisher_from_config(config.streamr)

        self.bus = RetinaEventBus(
            session_id=self.identity.session_id,
            jsonl_path=Path(config.jsonl_path) if config.jsonl_path else None,
            enable_ws=config.enable_ws,
            ws_host=config.ws_host,
            ws_port=config.ws_port,
            streamr_publisher=self.streamr_publisher,
            # Trio-retina
            trio_config=self.trio_config,
            session_identity=self.identity,
            visual_oracle_root_provider=None,  # Will be set after visual init
            posp_root_provider=None,  # Will be set after outcome init
            first_session_id=self.identity.session_id,  # Use current as first for now
            device_key=None,  # TODO: load from config
        )
        # DECK_BRIDGE_MARKER: RetinaEventBus -> Deck ws live (LIVE FEED ONLY - no mock)
        try:
            from qoresence.core import EventType as _ET  # local import to avoid cycle
            from qoresence.deck.server import push_moment as _deck_push
            from qoresence.deck.server import update_situation as _deck_update

            _deck_enabled = getattr(self.config, "deck_enabled", True)
            if _deck_enabled:

                def _on_bus_event(ev):  # type: ignore[no-untyped-def]
                    try:
                        et = getattr(ev, "type", None)
                        et_val = et.value if hasattr(et, "value") else str(et) if et else ""
                        payload = getattr(ev, "payload", None)
                        if payload is None and isinstance(ev, dict):
                            payload = ev.get("payload", ev)
                        if not isinstance(payload, dict):
                            return
                        # SituationModel lives in ClutchBot; we push structured snapshots
                        # Only push when this is a VISUAL_CONTEXT / OUTCOME / PRESENCE event
                        if et_val in (
                            _ET.VISUAL_CONTEXT.value,
                            _ET.OUTCOME_EVENT.value,
                            _ET.PRESENCE_REPORT.value,
                            _ET.GAME_DETECTED.value,
                        ):
                            sm = getattr(self, "situation_model", None)
                            if sm is not None:
                                s = sm.to_dict() if hasattr(sm, "to_dict") else {}
                                # require at least one live field; otherwise skip to avoid stale overlay
                                if s and any(
                                    s.get(k) is not None
                                    for k in (
                                        "home_score",
                                        "away_score",
                                        "quarter",
                                        "down",
                                        "game_state",
                                        "game_category",
                                    )
                                ):
                                    # latency_ms must be visual path time, never confidence
                                    lat = None
                                    try:
                                        vis = getattr(self, "visual", None)
                                        if vis is not None:
                                            ctx = vis.get_last_context()
                                            if ctx is not None:
                                                lat = getattr(ctx, "latency_ms", None)
                                    except Exception:
                                        pass
                                    _deck_update(s, latency_ms=lat)
                        # Direct moment / agent_action -> Deck Feed
                        # Skip A2A + clutchbot agent_action mirrors — DeckFeed backend
                        # already pushes scored chat once. Double-bridge caused spam.
                        if et_val == _ET.AGENT_ACTION.value:
                            agent = str(payload.get("agent_name") or "")
                            if agent in ("a2a", "clutchbot"):
                                return
                            title = payload.get("message") or payload.get("action") or ""
                            if isinstance(title, dict):
                                title = (
                                    title.get("text")
                                    or title.get("summary")
                                    or title.get("message")
                                    or ""
                                )
                            title = str(title).strip()
                            if title.startswith("{") and ("'text'" in title or '"text"' in title):
                                return
                            if title:
                                _deck_push(
                                    {
                                        "title": title[:80],
                                        "reason": str(payload.get("reason") or "")[:160],
                                        "clock": "now",
                                        "action": str(payload.get("action") or "chat"),
                                        "path": str(payload.get("path") or ""),
                                    }
                                )
                    except Exception:
                        pass

                def _on_moment_fallback(ev):  # type: ignore[no-untyped-def]
                    try:
                        payload = getattr(ev, "payload", None)
                        if payload is None and isinstance(ev, dict):
                            payload = ev
                        if isinstance(payload, dict) and payload.get("title"):
                            _deck_push(payload)
                    except Exception:
                        pass

                # Correct subscribe signature: subscribe(callback) -> unsubscribe
                try:
                    self.bus.subscribe(_on_bus_event)
                except Exception:
                    pass
                try:
                    self.bus.subscribe(_on_moment_fallback)
                except Exception:
                    pass
                import threading
                import time

                def _deck_poll():
                    # Fallback poll when bus events are sparse (1 Hz) - LIVE only
                    while True:
                        try:
                            sm = getattr(self, "situation_model", None)
                            if sm is None and getattr(self, "clutchbot", None) is not None:
                                sm = getattr(self.clutchbot, "_situation", None)
                                if sm is not None:
                                    # cache for next iteration
                                    try:
                                        object.__setattr__(self, "situation_model", sm)
                                    except Exception:
                                        self.situation_model = sm
                            if sm is not None and hasattr(sm, "to_dict"):
                                s = sm.to_dict()
                                # Include game_state/category so Lens can leave the
                                # center wait banner even when scorebug is still null.
                                if s and any(
                                    s.get(k) is not None
                                    for k in (
                                        "home_score",
                                        "away_score",
                                        "quarter",
                                        "down",
                                        "kills",
                                        "health",
                                        "game_state",
                                        "game_category",
                                    )
                                ):
                                    lat = None
                                    try:
                                        vis = getattr(self, "visual", None)
                                        if vis is not None:
                                            ctx = vis.get_last_context()
                                            if ctx is not None:
                                                lat = getattr(ctx, "latency_ms", None)
                                    except Exception:
                                        pass
                                    _deck_update(s, latency_ms=lat)
                        except Exception:
                            pass
                        time.sleep(1.0)

                threading.Thread(target=_deck_poll, name="deck-poll", daemon=True).start()
        except Exception:
            pass

        # Lobe runtimes
        self.streamer: StreamerRuntime | None = None
        self.controller: ControllerRuntime | None = None
        self.outcome: OutcomeRuntime | None = None
        self.screen: ScreenRuntime | None = None
        self.visual: VisualRuntime | None = None
        self.game_detector: GameAutoDetector | None = None
        self.fusion: PresenceFusionEngine | None = None

        # Agent runtimes
        self.clutchbot: ClutchBotAgent | None = None
        self.agent_glass = None
        # AgentGlass (glass D) — read-only spectator bridge, default OFF, no capture
        try:
            if getattr(self.config.agent_glass, "enabled", False):
                from qoresence.agents.agent_glass import start_agent_glass

                def _ag_situation_provider() -> dict:
                    sm = getattr(self, "situation_model", None)
                    if sm is None and getattr(self, "clutchbot", None) is not None:
                        sm = getattr(self.clutchbot, "_situation", None)
                    try:
                        if sm is not None and hasattr(sm, "to_dict"):
                            return sm.to_dict()
                        if isinstance(sm, dict):
                            return sm
                    except Exception:
                        pass
                    return {}

                self.agent_glass = start_agent_glass(
                    bus=self.bus,
                    config=self.config.agent_glass,
                    session_identity=self.identity,
                    situation_provider=_ag_situation_provider,
                )
                log.info(
                    "AgentGlass enabled (port %s host %s)",
                    getattr(self.config.agent_glass, "port", 8765),
                    getattr(self.config.agent_glass, "host", "127.0.0.1"),
                )
        except Exception as e:
            log.warning("AgentGlass init failed: %s", e)

        self.society = None
        try:
            soc = getattr(self.config, "society", None)
            if soc is not None and getattr(soc, "enabled", False):
                from qoresence.agents.society import start_society

                self.society = start_society(soc)
        except Exception as e:
            log.warning("Agent Society init failed: %s", e)

        # Input–Video Coupler (only when controller enabled)
        self.ivc = None

        # State
        self._running = False
        self._shutdown_event = threading.Event()

        # Stats
        self._start_time = 0.0

    def initialize_lobes(self) -> None:
        """Initialize enabled lobes from config."""
        # Streamer
        if self.config.streamer.enabled:
            self.streamer = StreamerRuntime(
                config=self.config.streamer,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
                presence_touch_file=Path(self.config.streamer.presence_touch_file)
                if getattr(self.config.streamer, "presence_touch_file", None)
                else None,
                presence_timeout_s=float(getattr(self.config.streamer, "presence_timeout_s", 5.0)),
            )
            log.info("Streamer lobe initialized")

        # Controller
        if self.config.controller.enabled:
            self.controller = ControllerRuntime(
                config=self.config.controller,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("Controller lobe initialized")

        # Outcome
        if self.config.outcome.enabled:
            self.outcome = OutcomeRuntime(
                config=self.config.outcome,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("Outcome lobe initialized")

        # Screen
        if self.config.screen.enabled:
            self.screen = ScreenRuntime(
                config=self.config.screen,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("Screen lobe initialized")

        # Visual
        if self.config.visual.enabled:
            self.visual = VisualRuntime(
                config=self.config.visual,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("Visual lobe initialized")

        # Game auto-detection (rich visual context for outcome + clutchbot)
        if self.config.game_detection.enabled and self.config.visual.enabled:
            self.game_detector = GameAutoDetector(
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
                vlm_client=self.visual._client,
                confidence_threshold=self.config.game_detection.confidence_threshold,
                stability_count=self.config.game_detection.stability_count,
                poll_interval_s=self.config.game_detection.poll_interval_s,
                learning_enabled=self.config.game_detection.learning_enabled,
                learning_path=Path(self.config.game_detection.learning_path)
                if self.config.game_detection.learning_path
                else None,
                ocr_provider=self.config.game_detection.ocr_provider,
                model_dir=Path(self.config.game_detection.vision_model_dir)
                if self.config.game_detection.vision_model_dir
                else None,
                game_profile=self.config.outcome.game_profile,
            )
            log.info("Game auto-detector initialized")

        # Fusion engine (always created for presence reports)
        self.fusion = create_fusion_engine(
            config=self.config,
            bus=self.bus,
        )
        log.info("Presence Fusion Engine initialized")

        # ClutchBot agent
        if self.config.clutchbot.enabled:
            self.clutchbot = ClutchBotAgent(
                config=self.config.clutchbot,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("ClutchBot agent initialized")

    def connect_lobes(self) -> None:
        """Connect lobe outputs to each other (cross-lobe integration)."""
        # Screen â† Controller (for coupling)
        if self.screen and self.controller:

            def controller_provider():
                # Return recent trigger/stick state as feature vector
                stats = self.controller.get_stats()
                return [stats.get("last_trigger", 0.0), stats.get("stick_motion", 0.0)]

            self.screen.set_controller_provider(controller_provider)

        # Visual â† Streamer/Screen (for frame provider)
        if self.visual:
            if self.streamer:

                def frame_provider():
                    return self.streamer.get_current_frame()

                self.visual.set_frame_provider(frame_provider)
            elif self.screen:

                def frame_provider():
                    return self.screen.get_current_frame()

                self.visual.set_frame_provider(frame_provider)

            # Visual â† Outcome/Controller/Screen (for cross-modal)
            def modality_provider():
                modalities = {}
                if self.outcome:
                    modalities["outcome"] = self.outcome.get_last_state()
                if self.controller:
                    modalities["controller"] = self.controller.get_stats()
                if self.screen:
                    modalities["screen"] = {
                        "coupling_score": 0.0
                    }  # Would need screen coupling access
                return modalities

            self.visual.set_modality_provider(modality_provider)

        # Game detector â† Streamer/Screen (frames) and â†’ Outcome (profile switch)
        if self.game_detector:
            if self.streamer:
                self.game_detector.set_frame_provider(self.streamer.get_current_frame)
            elif self.screen:
                self.game_detector.set_frame_provider(self.screen.get_current_frame)
            else:
                log.warning(
                    "Game auto-detection enabled but no frame source. "
                    "Add --screen or --streamer (or run `pip install qoresence[screen]`)."
                )

            if self.outcome:

                def switch_profile(profile_id):
                    self.outcome.set_game_profile(profile_id)

                self.game_detector.set_profile_switch_callback(switch_profile)

        # Fusion â† All lobes (lobe status updates)
        if self.fusion:
            if self.streamer:
                self.streamer.set_presence_callback(self.fusion.update_streamer_status)
            if self.controller:
                self.controller.set_presence_callback(self.fusion.update_controller_status)
            if self.outcome:
                self.outcome.set_presence_callback(self.fusion.update_outcome_status)
            if self.screen:
                self.screen.set_presence_callback(self.fusion.update_screen_status)
            if self.visual:
                self.visual.set_presence_callback(self.fusion.update_visual_status)

        # Trio-retina: set commitment root providers
        if self.trio_config and self.trio_config.enabled:
            # Visual oracle root provider
            if self.visual:

                def visual_root_provider():
                    # Get latest visual context state root
                    ctx = self.visual.get_last_context()
                    if ctx and ctx.confidence > 0.5:
                        import hashlib

                        state_str = f"{ctx.game_state}:{ctx.confidence}:{ctx.details}"
                        return hashlib.sha256(state_str.encode()).hexdigest()
                    return "b" * 64  # mock fallback

                self.bus._visual_oracle_root_provider = visual_root_provider

            # PoSP root provider
            if self.outcome:

                def posp_root_provider():
                    # Get latest outcome session root
                    state = self.outcome.get_last_state()
                    if state and state.get("last_event"):
                        import hashlib

                        state_str = f"{state['last_event']}:{state.get('home_score', 0)}:{state.get('away_score', 0)}"
                        return hashlib.sha256(state_str.encode()).hexdigest()
                    return "c" * 64  # mock fallback

                self.bus._posp_root_provider = posp_root_provider

    def start(self) -> bool:
        """Start all enabled lobes."""
        if self._running:
            log.warning("Already running")
            return True

        # Retina Deck -- start ws http://127.0.0.1:8765 if --deck/--play
        try:
            if getattr(self.config, "deck_enabled", False) and _start_deck is not None:
                _start_deck(
                    host=getattr(self.config, "deck_host", _DECK_HOST),
                    port=getattr(self.config, "deck_port", _DECK_PORT),
                    daemon=True,
                    config=self.config,
                )
                _dh = getattr(self.config, "deck_host", _DECK_HOST)
                _dp = getattr(self.config, "deck_port", _DECK_PORT)
                log.info(
                    "Retina Deck http://%s:%s  Lens /overlay.html  Rail /deck.html",
                    _dh,
                    _dp,
                )
                log.info(
                    "OBS Browser Source URL (not file://): http://%s:%s/overlay.html",
                    _dh,
                    _dp,
                )
        except Exception as e:
            log.warning("Deck start failed: %s", e)
        self._running = True
        self._start_time = time.time()

        # Initialize trio-retina validator
        if self.trio_config and self.trio_config.enabled:
            if self.bus.init_trio_validator():
                # Start validator in background
                asyncio.create_task(self.bus.start_trio_validator())
                log.info("Trio-retina validator started")

        # Start lobes
        if self.streamer and not self.streamer.start():
            log.error("Failed to start streamer")
            return False

        if self.controller and not self.controller.start():
            try:
                from qoresence.lobes.controller import list_controllers

                found = list_controllers()
                hint = (
                    ", ".join(
                        f"{c.get('product') or '?'} vid={int(c.get('vid') or 0):04x}"
                        for c in found[:5]
                    )
                    if found
                    else "none listed — plug DualSense USB / Remote Play"
                )
            except Exception:
                hint = 'check USB / Remote Play; python -c "from qoresence.lobes.controller import list_controllers; print(list_controllers())"'
            log.warning(
                "Controller failed to start (HID busy/permissions/missing) — "
                "continuing without controller; video path unchanged. Devices: %s",
                hint,
            )
            # don't return False — video stack continues

        # Input–Video Coupler when controller lobe is configured (even if HID open failed,
        # ring stays empty; coupling stays ~0)
        if self.config.controller.enabled:
            try:
                from qoresence.sync.ivc import start_ivc

                # Physical card: default 120 ms. Legacy VCam: set QORESENCE_IVC_LAG_HI_MS=200
                lag_hi = 120.0
                try:
                    import os as _os_ivc

                    lag_hi = float(_os_ivc.environ.get("QORESENCE_IVC_LAG_HI_MS", "120") or 120)
                    lag_hi = max(40.0, min(250.0, lag_hi))
                except Exception:
                    lag_hi = 120.0
                self.ivc = start_ivc(
                    bus=self.bus,
                    session_head_ns=self.identity.session_head_ns,
                    lag_lo_ms=20.0,
                    lag_hi_ms=lag_hi,
                )
            except Exception as e:
                log.warning("IVC failed to start: %s (video path continues)", e)

        if self.outcome:
            self.outcome.start()

        if self.screen and not self.screen.start():
            log.error("Failed to start screen")
            return False

        if self.visual and not self.visual.start():
            log.error("Failed to start visual")
            return False

        if self.game_detector:
            self.game_detector.start()

        if self.fusion:
            self.fusion.start()

        if self.clutchbot:
            self.clutchbot.start()

        log.info("Qoresence started: session=%s", self.identity.session_id)
        # Visible no-frame diagnostic (do not crash Deck if video is late/missing)
        if self.config.streamer.enabled:
            self._schedule_no_frame_watch()
        return True

    def _schedule_no_frame_watch(self) -> None:
        """After N seconds, log ERROR if streamer never produced a frame."""
        import os
        import threading

        try:
            wait_s = float(os.environ.get("QORESENCE_NO_FRAME_WAIT_S", "10") or 10)
            wait_s = max(5.0, min(60.0, wait_s))
        except Exception:
            wait_s = 10.0

        def _check() -> None:
            try:
                if not self._running:
                    return
                st = self.streamer
                if st is None:
                    return
                # Prefer frames_processed / last success if available
                frames = 0
                idx = getattr(getattr(st, "config", None), "device_index", None)
                name = getattr(st, "_bound_device_name", None) or getattr(
                    st, "_preferred_device_name", None
                )
                try:
                    frames = int(getattr(st, "_frames_processed", 0) or 0)
                except Exception:
                    frames = 0
                has = frames > 0
                if not has:
                    try:
                        fr = st.get_current_frame()
                        has = fr is not None
                    except Exception:
                        has = False
                if has:
                    return
                log.error(
                    "NO FRAME after %.0fs — capture not flowing "
                    "(device_index=%s name=%r frames_processed=%s). "
                    "Run: python -m qoresence.cli --streamer-list. "
                    "If OBS holds the physical card, free it (Pattern B) or use "
                    "OBS Virtual Camera index (Pattern A). See docs/CAPTURE_OWNERSHIP.md",
                    wait_s,
                    idx,
                    name,
                    frames,
                )
            except Exception as e:
                log.debug("no-frame watch: %s", e)

        threading.Timer(wait_s, _check).start()

    def stop(self) -> None:
        """Stop all lobes gracefully."""
        if not self._running:
            return

        self._running = False
        log.info("Shutting down...")

        # Stop trio-retina validator
        if self.trio_config and self.trio_config.enabled:
            asyncio.create_task(self.bus.stop_trio_validator())
            log.info("Trio-retina validator stopped")

        if self.fusion:
            self.fusion.stop()

        if self.clutchbot:
            self.clutchbot.stop()

        if self.game_detector:
            self.game_detector.stop()

        if self.visual:
            self.visual.stop()

        if self.screen:
            self.screen.stop()

        if self.outcome:
            self.outcome.stop()

        if self.ivc is not None:
            try:
                from qoresence.sync.ivc import stop_ivc

                stop_ivc()
            except Exception:
                pass
            self.ivc = None

        if self.controller:
            self.controller.stop()

        if self.streamer:
            self.streamer.stop()

        if getattr(self, "agent_glass", None) is not None:
            try:
                from qoresence.agents.agent_glass import stop_agent_glass

                stop_agent_glass()
            except Exception:
                pass
            self.agent_glass = None

        if getattr(self, "society", None) is not None:
            try:
                from qoresence.agents.society import stop_society

                stop_society()
            except Exception:
                pass
            self.society = None

        if self.streamr_publisher:
            self.streamr_publisher.stop()

        self.bus.close()

        elapsed = time.time() - self._start_time
        log.info("Qoresence stopped after %.1fs", elapsed)

    def wait_for_shutdown(self) -> None:
        """Block until shutdown signal."""
        self._shutdown_event.wait()

    def signal_shutdown(self) -> None:
        """Signal shutdown from signal handler."""
        self._shutdown_event.set()

    def get_status(self) -> dict:
        """Get application status."""
        status = {
            "session_id": self.identity.session_id,
            "running": self._running,
            "uptime_s": round(time.time() - self._start_time, 1),
            "lobes": {
                "streamer": self.streamer.is_running() if self.streamer else False,
                "controller": self.controller.is_running() if self.controller else False,
                "outcome": self.outcome.is_running() if self.outcome else False,
                "screen": self.screen.is_running() if self.screen else False,
                "visual": self.visual.is_running() if self.visual else False,
                "fusion": self.fusion.is_running() if self.fusion else False,
            },
            "bus_stats": self.bus.stats(),
        }
        if self.trio_config and self.trio_config.enabled:
            status["trio_retina"] = self.bus.get_trio_stats()
        return status


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# HEALTH CHECKS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def run_health_checks(app: QoresenceApp) -> dict:
    """Run health checks on all components."""
    checks = {
        "timestamp_ns": clock_ns(),
        "session_id": app.identity.session_id,
        "overall": "healthy",
        "components": {},
    }

    # Check event bus
    bus_stats = app.bus.stats() if hasattr(app.bus, "stats") else app.bus.get_stats()  # type: ignore
    checks["components"]["event_bus"] = {
        "status": "healthy" if bus_stats.get("subscribers", 0) >= 0 else "degraded",
        "details": bus_stats,
    }

    # Check each lobe
    if app.streamer:
        checks["components"]["streamer"] = {
            "status": "healthy" if app.streamer.is_running() else "stopped",
            "details": {"running": app.streamer.is_running()},
        }

    if app.controller:
        checks["components"]["controller"] = {
            "status": "healthy" if app.controller.is_running() else "stopped",
            "details": {"running": app.controller.is_running()},
        }

    if app.screen:
        checks["components"]["screen"] = {
            "status": "healthy" if app.screen.is_running() else "stopped",
            "details": {"running": app.screen.is_running()},
        }

    if app.outcome:
        checks["components"]["outcome"] = {
            "status": "healthy" if app.outcome.is_running() else "stopped",
            "details": {"running": app.outcome.is_running()},
        }

    if app.visual:
        checks["components"]["visual"] = {
            "status": "healthy" if app.visual.is_running() else "stopped",
            "details": {"running": app.visual.is_running()},
        }

    if app.fusion:
        fusion_stats = app.fusion.get_lobe_stats()
        checks["components"]["fusion"] = {
            "status": "healthy",
            "details": fusion_stats,
        }

    # Check trio-retina
    if app.trio_config and app.trio_config.enabled:
        trio_stats = app.bus.get_trio_stats()
        checks["components"]["trio_retina"] = {
            "status": "healthy" if trio_stats.get("enabled", False) else "disabled",
            "details": trio_stats,
        }

    # Overall status
    for _comp, info in checks["components"].items():
        if info["status"] != "healthy":
            checks["overall"] = "degraded"
            break

    return checks


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# CLI ENTRY POINT
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def apply_society_cli(config: RetinaUnifiedConfig, args) -> RetinaUnifiedConfig:
    """--play turns Agent Society on (all roles). --no-agent-society opts out."""
    from dataclasses import replace

    from qoresence.agents.society.config import AgentSocietyConfig, _csv_roles, resolve_key_file
    from qoresence.agents.society.types import KNOWN_ROLES

    base = getattr(config, "society", None) or AgentSocietyConfig.from_env()
    if not isinstance(base, AgentSocietyConfig):
        base = AgentSocietyConfig.from_env()
    if getattr(args, "no_agent_society", False):
        return replace(config, society=replace(base, enabled=False))
    if (
        getattr(args, "play", False)
        or getattr(args, "agent_society", False)
        or getattr(args, "agent_society_roles", None)
    ):
        raw = getattr(args, "agent_society_roles", None)
        if raw:
            roles = _csv_roles(raw)
        elif getattr(args, "play", False):
            roles = KNOWN_ROLES
        else:
            roles = base.roles
        key_file = resolve_key_file(getattr(base, "api_key_file", None))
        return replace(config, society=replace(base, enabled=True, roles=roles, api_key_file=key_file))
    return config


def create_config_from_args(args) -> RetinaUnifiedConfig:
    """Create config from CLI arguments."""
    from dataclasses import replace

    config = RetinaUnifiedConfig(
        session_id=args.session_id or "",
        session_head_ns=args.session_head_ns or 0,
        device_id_hex=args.device_id or "",
        jsonl_path=args.jsonl_path or "",
        enable_ws=args.enable_ws,
        ws_host=args.ws_host,
        ws_port=args.ws_port,
    )

    # Default frame source for --stream: screen if available, unless user picked streamer.
    if args.stream and not args.screen and not args.streamer:
        try:
            import importlib.util

            if importlib.util.find_spec("mss"):
                args.screen = True
                args.screen_fps = min(args.screen_fps, 5.0)
                log.debug("--stream: defaulting to screen capture (5 fps)")
        except Exception:
            pass

    # Stream preset: enable the minimal ClutchBot capture stack
    if args.stream:
        config.enable_ws = True
        config.outcome = replace(config.outcome, enabled=True, game_profile=args.game_profile)
        config.visual = replace(
            config.visual,
            enabled=True,
            prefer_local=True,
            local_fallback=True,
            frame_sample_rate=args.visual_sample_rate,
            game_profile=args.game_profile or config.visual.game_profile,
        )
        config.game_detection = replace(
            config.game_detection, enabled=getattr(args, "game_detect", True)
        )

    if getattr(args, "game_detect", False):
        config.game_detection = replace(config.game_detection, enabled=True)
    if getattr(args, "no_game_detect", False):
        config.game_detection = replace(config.game_detection, enabled=False)

    # Game detection tuning
    config.game_detection = replace(
        config.game_detection,
        confidence_threshold=getattr(
            args, "game_detect_confidence", config.game_detection.confidence_threshold
        ),
        stability_count=getattr(
            args, "game_detect_stability", config.game_detection.stability_count
        ),
        poll_interval_s=getattr(args, "game_detect_poll", config.game_detection.poll_interval_s),
    )

    # Honor VisualConfig env overrides even when launched via --stream (fix 401 fallback)
    import os as _os

    _prefer = _os.environ.get("QORESENCE_VISUAL_PREFER_LOCAL", "").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    _fallback_env = _os.environ.get("QORESENCE_VISUAL_LOCAL_FALLBACK", "")
    _fallback = True if _fallback_env == "" else _fallback_env.lower() in ("1", "true", "yes", "on")
    _local_model = _os.environ.get("QORESENCE_VISUAL_LOCAL_MODEL") or None
    if _prefer or _local_model is not None or _fallback_env != "":
        from dataclasses import replace as _replace2

        config.visual = _replace2(
            config.visual,
            prefer_local=_prefer or config.visual.prefer_local,
            local_fallback=_fallback,
            local_model_path=_local_model or config.visual.local_model_path,
        )
    # CLI flag override (if added)
    if getattr(args, "visual_prefer_local", False):
        from dataclasses import replace as _replace3

        config.visual = _replace3(config.visual, prefer_local=True)

    # Enable lobes based on flags
    if args.streamer:
        _sd = int(getattr(args, "streamer_device", -1))
        try:
            from qoresence.lobes.streamer import resolve_capture_device

            _r = resolve_capture_device(
                None if _sd < 0 else _sd,
                prefer_name="USB3.0 Video",
                allow_obs_vcam=False,
            )
            if _r is not None:
                _sd = _r[0]
        except Exception:
            pass
        config.streamer = replace(
            config.streamer,
            enabled=True,
            device_index=_sd,
            device_name="USB3.0 Video",
            backend=getattr(args, "streamer_backend", "dshow"),
            width=getattr(args, "streamer_width", 1280),
            height=getattr(args, "streamer_height", 720),
            fps_target=args.streamer_fps,
        )
    if args.streamr:
        _event_types = (
            [t.strip() for t in args.streamr_event_types.split(",") if t.strip()]
            if args.streamr_event_types
            else []
        )
        if args.streamr_stream_id:
            config.streamr = replace(
                config.streamr,
                enabled=True,
                stream_id=args.streamr_stream_id,
                protocol=args.streamr_protocol,
                host=args.streamr_host,
                port=args.streamr_port,
                api_key=args.streamr_api_key,
                event_types=_event_types,
                max_eps=args.streamr_max_eps,
            )
    if args.controller:
        config.controller = replace(
            config.controller, enabled=True, poll_rate_hz=args.controller_rate
        )
    if args.outcome:
        config.outcome = replace(config.outcome, enabled=True, game_profile=args.game_profile)
    if args.screen:
        config.screen = replace(config.screen, enabled=True, fps_target=args.screen_fps)
    if args.visual:
        _vlm_extra = {}
        if getattr(args, "visual_local_model", None):
            _vlm_extra["local_model_path"] = args.visual_local_model
        if getattr(args, "visual_prefer_local", False):
            _vlm_extra["prefer_local"] = True
        config.visual = replace(
            config.visual,
            enabled=True,
            prefer_local=True,
            local_fallback=True,
            frame_sample_rate=args.visual_sample_rate,
            game_profile=getattr(args, "game_profile", None) or config.visual.game_profile,
            **_vlm_extra,
        )

    # AgentGlass wiring — independent of ClutchBot / --stream.
    # Must apply for --play --deck --agent-glass (and env) or glass stays disabled.
    try:
        if getattr(args, "no_agent_glass", False):
            config.agent_glass = replace(config.agent_glass, enabled=False)
        elif getattr(args, "agent_glass", False):
            _ag_updates = {"enabled": True}
            if getattr(args, "agent_glass_token_file", None):
                _ag_updates["token_file"] = args.agent_glass_token_file
            if getattr(args, "agent_glass_no_frame", False):
                _ag_updates["allow_frame"] = False
            config.agent_glass = replace(config.agent_glass, **_ag_updates)
        else:
            # --agent-glass-token-file / --agent-glass-no-frame keep env as source of truth
            if getattr(args, "agent_glass_token_file", None):
                config.agent_glass = replace(
                    config.agent_glass, token_file=args.agent_glass_token_file
                )
            if getattr(args, "agent_glass_no_frame", False):
                config.agent_glass = replace(config.agent_glass, allow_frame=False)
        config = apply_society_cli(config, args)
    except Exception:
        pass

    # ClutchBot agent (explicit or via --stream preset)
    if args.clutchbot or args.stream:
        from pathlib import Path as _P_cb

        _tok_file = args.clutchbot_token_file
        if not _tok_file and _P_cb(".secrets/twitch_oauth.txt").exists():
            _tok_file = ".secrets/twitch_oauth.txt"
        _ch = (args.clutchbot_channel or "").strip()
        _tw_enabled = bool(
            _ch and (args.clutchbot_username or _ch) and (args.clutchbot_token or _tok_file)
        )
        _llm_key = ".secrets/quicksilver_clutchbot.key"
        config.clutchbot = replace(
            config.clutchbot,
            enabled=True,
            enable_chat=not args.clutchbot_no_chat,
            clip_has_delay=not args.clutchbot_no_clip_delay,
            deck_enabled=True,
            llm_enabled=config.clutchbot.llm_enabled or _P_cb(_llm_key).exists(),
            llm_api_key_file=config.clutchbot.llm_api_key_file
            or (_llm_key if _P_cb(_llm_key).exists() else None),
            a2a_enabled=bool(getattr(args, "a2a", False) or config.clutchbot.a2a_enabled),
            twitch=TwitchConfig(
                enabled=_tw_enabled or args.clutchbot_channel != "",
                channel=args.clutchbot_channel,
                bot_username=args.clutchbot_username or args.clutchbot_channel,
                oauth_token=args.clutchbot_token,
                token_file=_tok_file,
                helix_token=args.clutchbot_helix_token,
                helix_token_file=args.clutchbot_helix_token_file,
                client_id=args.clutchbot_client_id,
                client_secret=args.clutchbot_client_secret,
                broadcaster_id=args.clutchbot_broadcaster_id,
                broadcaster_username=args.clutchbot_broadcaster_username
                or args.clutchbot_channel
                or None,
                message_interval_s=args.clutchbot_interval,
                enable_clips=args.clutchbot_enable_clips,
                enable_predictions=args.clutchbot_enable_predictions,
                enable_follow_alerts=args.clutchbot_enable_follow_alerts,
                enable_sub_alerts=args.clutchbot_enable_sub_alerts,
                enable_redemption_alerts=args.clutchbot_enable_redemption_alerts,
            ),
        )

    # Studio / Ghost Cut wiring
    if (
        args.foundry_reel
        or args.render_reels
        or args.foundry_reel_clip
        or getattr(args, "studio", False)
    ):
        from dataclasses import replace as _replace_studio

        _enabled = bool(
            args.foundry_reel
            or args.render_reels
            or args.foundry_reel_clip
            or getattr(args, "studio", False)
        )
        _out_dir = args.foundry_reel_output_dir
        config.studio = _replace_studio(
            config.studio,
            enabled=_enabled,
            max_reels_per_session=int(args.foundry_reel_count or 3),
            output_dir=_out_dir if _out_dir else config.studio.output_dir,
        )

    return config


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="qoresence",
        description="Qoresence - Local game-state capture + Twitch ClutchBot",
    )

    # Session identity
    parser.add_argument("--session-id", help="Session ID (auto-generated if not provided)")
    parser.add_argument("--session-head-ns", type=int, help="Session head timestamp (ns)")
    parser.add_argument("--device-id", help="Device ID (16-char hex)")

    # Output
    parser.add_argument("--jsonl-path", help="Path to JSONL output file")
    parser.add_argument("--enable-ws", action="store_true", help="Enable WebSocket broadcast")
    parser.add_argument("--ws-host", default="127.0.0.1", help="WebSocket host")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket port")

    # One-shot presets
    parser.add_argument(
        "--stream",
        action="store_true",
        help="ClutchBot streaming preset: enables outcome, visual, clutchbot, and WebSocket",
    )

    # Lobes
    parser.add_argument("--streamer", action="store_true", help="Enable streamer lobe (UVC/OBS)")
    parser.add_argument(
        "--streamer-list", action="store_true", help="List DirectShow capture devices and exit"
    )
    parser.add_argument(
        "--streamer-fps",
        type=float,
        default=30.0,
        help="Streamer capture FPS (use 60 under --play for PS5 60 Hz so capture matches LIVE ring)",
    )
    parser.add_argument(
        "--streamer-device",
        type=int,
        default=-1,
        help="Streamer DShow device index. Default -1 = auto-pick physical card by name "
        "(USB3.0 Video / HDMI) so unplug/replug index shifts still work. "
        "Pass a fixed index only if needed; OBS Virtual Camera is legacy.",
    )
    parser.add_argument(
        "--streamer-backend",
        choices=["auto", "dshow", "msmf"],
        default="dshow",
        help="Capture backend (dshow recommended for USB3.0 Video, msmf for some cards)",
    )
    parser.add_argument("--streamer-width", type=int, default=1280, help="Capture width")
    parser.add_argument("--streamer-height", type=int, default=720, help="Capture height")

    # Streamr Network publisher
    parser.add_argument(
        "--streamr", action="store_true", help="Publish events to a local Streamr node"
    )
    parser.add_argument(
        "--streamr-stream-id",
        type=str,
        default="",
        help="Streamr stream ID, e.g. 0x.../qoresence/football",
    )
    parser.add_argument(
        "--streamr-protocol",
        choices=["http", "mqtt", "websocket"],
        default="http",
        help="Local Streamr node interface protocol",
    )
    parser.add_argument(
        "--streamr-host", type=str, default="127.0.0.1", help="Local Streamr node host"
    )
    parser.add_argument("--streamr-port", type=int, default=7171, help="Local Streamr node port")
    parser.add_argument("--streamr-api-key", type=str, default=None, help="Streamr node API key")
    parser.add_argument(
        "--streamr-event-types",
        type=str,
        default="",
        help="Comma-separated event types to publish (e.g. 'presence_report,visual_context' or '*' for all)",
    )
    parser.add_argument(
        "--streamr-max-eps",
        type=float,
        default=0.0,
        help="Max events per second throttle (0 = off)",
    )

    parser.add_argument(
        "--controller",
        action="store_true",
        help="Enable controller lobe (HID DualSense) + InputRing + IVC. Default OFF.",
    )
    parser.add_argument(
        "--controller-rate", type=float, default=1000.0, help="Controller poll rate (Hz)"
    )
    parser.add_argument("--outcome", action="store_true", help="Enable outcome lobe (game events)")
    parser.add_argument(
        "--game-profile",
        choices=[
            "ncaa_football_27",
            "call_of_duty",
            "madden_27",
            "madden_2027",
            "ncaa_27",
            "college_football_27",
            "ea_sports_college_football_27",
            "cod",
            "modern_warfare",
            "warzone",
        ],
        default="ncaa_football_27",
        help="Game profile (supports common aliases)",
    )
    parser.add_argument(
        "--scoreboard-home-left",
        action="store_true",
        help="Scoreboard puts the HOME team on the LEFT (default is away-left / home-right)",
    )
    parser.add_argument("--screen", action="store_true", help="Enable screen lobe (mss/DXGI)")
    parser.add_argument("--screen-fps", type=float, default=60.0, help="Screen capture FPS")
    parser.add_argument("--visual", action="store_true", help="Enable visual lobe (VLM)")
    parser.add_argument(
        "--visual-sample-rate", type=int, default=30, help="Visual frame sample rate"
    )
    parser.add_argument(
        "--visual-prefer-local",
        action="store_true",
        help="Use LocalVLMClient (heuristic/ONNX) instead of cloud VLM",
    )
    parser.add_argument(
        "--visual-local-model", default=None, help="Path to qoresence-vlm-distilled.onnx"
    )

    # Game detection (rich visual context for outcome/clutchbot)
    parser.add_argument(
        "--game-detect",
        action="store_true",
        help="Enable game auto-detection (enabled by --stream)",
    )
    parser.add_argument(
        "--no-game-detect", action="store_true", help="Disable game auto-detection even in --stream"
    )
    parser.add_argument(
        "--game-detect-confidence",
        type=float,
        default=0.65,
        help="Game detection confidence threshold",
    )
    parser.add_argument(
        "--game-detect-stability", type=int, default=2, help="Consecutive detections required"
    )
    parser.add_argument(
        "--game-detect-poll", type=float, default=3.0, help="Game detection poll interval (s)"
    )

    # ClutchBot (Twitch agent)
    parser.add_argument("--clutchbot", action="store_true", help="Enable ClutchBot Twitch agent")
    parser.add_argument(
        "--clutchbot-channel", default="", help="Twitch channel for the bot to join (no #)"
    )
    parser.add_argument("--clutchbot-username", default="", help="Twitch bot username")
    parser.add_argument("--clutchbot-token", default=None, help="Twitch bot OAuth token")
    parser.add_argument(
        "--clutchbot-token-file", default=None, help="File containing the Twitch bot OAuth token"
    )
    parser.add_argument(
        "--clutchbot-helix-token",
        default=None,
        help="Twitch Helix access token (for clips/predictions)",
    )
    parser.add_argument(
        "--clutchbot-helix-token-file", default=None, help="File containing the Twitch Helix token"
    )
    parser.add_argument("--clutchbot-client-id", default=None, help="Twitch application Client ID")
    parser.add_argument(
        "--clutchbot-client-secret", default=None, help="Twitch application Client Secret"
    )
    parser.add_argument(
        "--clutchbot-broadcaster-id", default=None, help="Twitch broadcaster user ID"
    )
    parser.add_argument(
        "--clutchbot-broadcaster-username", default=None, help="Twitch broadcaster login name"
    )
    parser.add_argument(
        "--clutchbot-interval",
        type=float,
        default=2.0,
        help="Minimum seconds between sent IRC messages",
    )
    parser.add_argument(
        "--clutchbot-no-chat", action="store_true", help="Disable chat/greeting actions"
    )
    parser.add_argument(
        "--clutchbot-enable-clips", action="store_true", help="Create clips on clutch moments"
    )
    parser.add_argument(
        "--clutchbot-no-clip-delay",
        action="store_true",
        help="Disable delay when creating clips (default: has delay)",
    )
    parser.add_argument(
        "--clutchbot-enable-predictions",
        action="store_true",
        help="Start channel-point predictions",
    )
    parser.add_argument(
        "--clutchbot-enable-follow-alerts", action="store_true", help="EventSub follow alerts"
    )
    parser.add_argument(
        "--clutchbot-enable-sub-alerts", action="store_true", help="EventSub subscription alerts"
    )
    parser.add_argument(
        "--clutchbot-enable-redemption-alerts",
        action="store_true",
        help="EventSub redemption alerts",
    )
    parser.add_argument(
        "--a2a",
        action="store_true",
        help="Enable A2A bus (Gemini scene ↔ DeepSeek chat via Quicksilver). "
        "Also QORESENCE_A2A=1. Live agents: QORESENCE_A2A_GEMINI=1 QORESENCE_A2A_DEEPSEEK=1.",
    )

    # Trio-retina (w3bstream validation)
    parser.add_argument(
        "--trio", action="store_true", help="Enable trio-retina w3bstream validation"
    )
    parser.add_argument(
        "--trio-wasm-path", default="w3bstream_applet.wasm", help="Path to w3bstream applet WASM"
    )
    parser.add_argument(
        "--trio-validate-on-ingest", action="store_true", help="Validate each event at ingestion"
    )
    parser.add_argument(
        "--trio-validate-on-flush",
        action="store_true",
        default=True,
        help="Validate batched events periodically",
    )
    parser.add_argument(
        "--trio-flush-interval", type=float, default=30.0, help="Batch flush interval (seconds)"
    )
    parser.add_argument(
        "--trio-block-rpc",
        default="https://babel-api.testnet.iotex.io",
        help="IoTeX RPC for block number",
    )
    parser.add_argument(
        "--trio-node-session-verify",
        action="store_true",
        help="Enable DEPIN-1 LEG 2 node/session gate",
    )
    parser.add_argument(
        "--trio-events-root-verify", action="store_true", help="Verify events root (merkle)"
    )

    # Options
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="Exquisite play mode: streamer+visual+fusion+clutchbot+deck (while playing)",
    )
    parser.add_argument(
        "--deck", action="store_true", help="Enable Retina Deck ws://127.0.0.1:8765 (Lens+Rail)"
    )
    parser.add_argument("--deck-host", default="127.0.0.1", help="Deck host")
    parser.add_argument("--deck-port", type=int, default=8765, help="Deck port")
    parser.add_argument("--health-check", action="store_true", help="Run health checks and exit")
    parser.add_argument("--dry-run", action="store_true", help="Initialize but don't start lobes")
    parser.add_argument(
        "--monitor",
        action="store_true",
        help="Open native Retina Monitor (FrameHub blit; no second capture). Default OFF.",
    )
    parser.add_argument(
        "--monitor-max-width",
        type=int,
        default=1280,
        help="Retina Monitor max display width (default 1280)",
    )
    parser.add_argument(
        "--monitor-preset",
        choices=["minimal", "situation", "full"],
        default="full",
        help="Retina Monitor HUD layout preset (default full). Cycle live with 'p' key.",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Show system tray icon with live status (score, sync). Default OFF.",
    )
    parser.add_argument(
        "--agent-glass",
        action="store_true",
        help="Enable AgentGlass spectator API (glass D, localhost-only, default OFF)",
    )
    parser.add_argument(
        "--no-agent-glass", action="store_true", help="Disable AgentGlass even if env enabled"
    )
    parser.add_argument(
        "--agent-glass-token-file",
        default=None,
        help="AgentGlass token file (default .secrets/agent_glass.token)",
    )
    parser.add_argument(
        "--agent-glass-no-frame", action="store_true", help="Disable AgentGlass frame endpoint"
    )
    parser.add_argument(
        "--agent-society",
        action="store_true",
        help="Enable Agent Society (also auto-on with --play)",
    )
    parser.add_argument(
        "--no-agent-society",
        action="store_true",
        help="Disable Agent Society even under --play",
    )
    parser.add_argument(
        "--agent-society-roles",
        default=None,
        help="CSV roles: spam_warden,pilot_auditor,drive_coach,ghost_editor,prediction_steward",
    )
    parser.add_argument(
        "--society-audit",
        action="store_true",
        help="One-shot pilot_auditor closeout (no --play) then exit",
    )
    parser.add_argument(
        "--society-propose-cuts",
        action="store_true",
        help="One-shot ghost_editor proposals (no --play) then exit",
    )
    parser.add_argument(
        "--profiles-list",
        action="store_true",
        help="List all registered game profiles (built-in + community) and exit.",
    )
    parser.add_argument(
        "--audit",
        nargs="?",
        const="10",
        type=int,
        metavar="N",
        help="Print the last N evidence chains and router decisions from the JSONL log, then exit.",
    )
    parser.add_argument(
        "--audit-jsonl",
        default=None,
        help="Path to JSONL log for --audit (default: --jsonl-path or logs/events.jsonl).",
    )

    # Foundry Bay / Ghost Cut (default OFF, local)
    parser.add_argument(
        "--studio",
        action="store_true",
        help="Enable Foundry Bay on Deck (local Ghost Cut). Does not start a one-shot cut.",
    )
    parser.add_argument(
        "--foundry-reel",
        action="store_true",
        help="Cut local Ghost highlights from Foundry clips (one-shot if not combined with --play/--deck)",
    )
    parser.add_argument(
        "--render-reels",
        action="store_true",
        help="Alias for --foundry-reel",
    )
    parser.add_argument(
        "--foundry-reel-clip",
        default=None,
        help="Cut a Ghost highlight from one clip (path or stem) and exit",
    )
    parser.add_argument(
        "--foundry-reel-count",
        type=int,
        default=3,
        help="Max Ghost Cuts per session (default 3)",
    )
    parser.add_argument(
        "--foundry-reel-output-dir",
        default=None,
        help="Directory for Ghost Cuts (default: clips/<stem>_cut/)",
    )
    parser.add_argument(
        "--foundry-reel-kinds",
        default=None,
        help="Comma-separated chapter kinds to target (e.g. confirm,score_changed)",
    )
    parser.add_argument(
        "--foundry-reel-no-wait",
        action="store_true",
        help="With --play/--deck: queue Ghost Cuts and keep running. One-shot mode always waits.",
    )

    args = parser.parse_args()

    # Scoreboard orientation override: env is authoritative for the extractor.
    if getattr(args, "scoreboard_home_left", False):
        os.environ["QORESENCE_SCOREBOARD_HOME_LEFT"] = "1"

    # Load community game profiles from profiles/ directory
    try:
        from qoresence.profiles.sdk import load_community_profiles

        _n = load_community_profiles()
        if _n:
            log.info("Loaded %d community game profile(s) from profiles/", _n)
    except Exception as e:
        log.debug("Community profiles load skipped: %s", e)

    # List all profiles and exit
    if getattr(args, "profiles_list", False):
        from qoresence.profiles.sdk import list_profiles

        profiles = list_profiles()
        if not profiles:
            print("No game profiles registered.")  # noqa: T201
        else:
            print(f"{'ID':<25} {'Name':<35} {'Cat':<10} {'Ev':<4} {'Fld':<4} {'Type'}")  # noqa: T201
            print("-" * 90)  # noqa: T201
            for p in profiles:
                ptype = "community" if p["community"] else "built-in"
                print(  # noqa: T201
                    f"{p['profile_id']:<25} {p['display_name']:<35} {p['category']:<10} "
                    f"{p['event_count']:<4} {p['field_count']:<4} {ptype}"
                )
        sys.exit(0)

    # Audit: print evidence chains and router decisions from JSONL log
    if getattr(args, "audit", None) is not None:
        _audit_path = (
            getattr(args, "audit_jsonl", None)
            or getattr(args, "jsonl_path", None)
            or "logs/events.jsonl"
        )
        _run_audit(_audit_path, args.audit)
        sys.exit(0)

    # Single-instance guard for play/deck — dual processes freeze DShow capture
    if getattr(args, "play", False) or getattr(args, "deck", False):
        if not _acquire_pilot_lock(int(getattr(args, "deck_port", 8765) or 8765)):
            print(  # noqa: T201
                "ERROR: Another Qoresence play/deck instance is already running "
                f"(port {getattr(args, 'deck_port', 8765)} / lock file). "
                "Stop the other window (Ctrl+C) first — dual open freezes the capture card.",
                file=sys.stderr,
            )
            sys.exit(2)

    if args.streamer_list:
        from qoresence.lobes.streamer import (
            _is_obs_virtual_camera_name,
            list_dshow_devices,
        )

        devices = list_dshow_devices()
        if not devices:
            print("No DirectShow capture devices found (pygrabber may not be installed).")  # noqa: T201
            sys.exit(0)
        # Index | Allowed | Backend | Name [annotation]
        print(f"{'Index':<6} {'Allowed':<8} {'Backend':<8} {'Name'}")  # noqa: T201
        print("-" * 78)  # noqa: T201
        for row in devices:
            if len(row) >= 4:
                idx, name, allowed, backend = row[0], row[1], row[2], row[3]
            else:
                idx, name, allowed = row[0], row[1], row[2]
                backend = "dshow"
            status = "OK" if allowed else "BLOCKED"
            note = ""
            if allowed and not _is_obs_virtual_camera_name(name) and "camera" not in name.lower():
                note = "  [recommended — Qoresence owns card]"
            elif _is_obs_virtual_camera_name(name):
                note = "  [legacy — only if OBS owns physical card]"
            print(f"{idx:<6} {status:<8} {backend:<8} {name}{note}")  # noqa: T201
        print("")  # noqa: T201
        print(  # noqa: T201
            "Recommended: Qoresence owns physical HDMI. Default --streamer-device -1 auto-picks "
            "USB3.0 Video by name (survives unplug/replug index changes). "
            "Close OBS Video Capture on that device first. See docs/OBS_OWNS_CARD.md"
        )
        sys.exit(0)

    setup_logging(args.log_level)

    # Create trio-retina config (CLI args take precedence over env vars)
    trio_config = None
    trio_enabled = args.trio or os.environ.get("QORESENCE_TRIO_ENABLED", "0") == "1"
    if TRIO_AVAILABLE and trio_enabled:
        trio_config = TrioRetinaConfig(
            enabled=True,
            wasm_path=args.trio_wasm_path
            or os.environ.get("QORESENCE_TRIO_WASM_PATH", "w3bstream_applet.wasm"),
            validate_on_ingest=args.trio_validate_on_ingest
            or os.environ.get("QORESENCE_TRIO_VALIDATE_ON_INGEST", "0") == "1",
            validate_on_flush=args.trio_validate_on_flush
            or os.environ.get("QORESENCE_TRIO_VALIDATE_ON_FLUSH", "1") == "1",
            flush_interval_s=float(
                args.trio_flush_interval or os.environ.get("QORESENCE_TRIO_FLUSH_INTERVAL", "30.0")
            ),
            block_rpc_url=args.trio_block_rpc
            or os.environ.get("QORESENCE_TRIO_BLOCK_RPC", "https://babel-api.testnet.iotex.io"),
            node_session_verify=args.trio_node_session_verify
            or os.environ.get("QORESENCE_TRIO_NODE_SESSION_VERIFY", "0") == "1",
            retina_events_root_verify=args.trio_events_root_verify
            or os.environ.get("QORESENCE_TRIO_EVENTS_ROOT_VERIFY", "0") == "1",
        )
        log.info("Trio-retina validation enabled")

    # Create config
    config = create_config_from_args(args)
    # --play / --deck wiring (Retina Deck exquisite while playing) — LIVE FEED CONTRACT
    # --play: HDMI streamer (DShow) + visual(local) + outcome + clutchbot + deck.
    # Default frame source is USB/HDMI capture — NOT mss desktop (monitor 0).
    # Use --screen only if you intentionally want desktop capture as fallback.
    if getattr(args, "play", False):
        try:
            object.__setattr__(config, "deck_enabled", True)
            object.__setattr__(config, "deck_host", getattr(args, "deck_host", "127.0.0.1"))
            object.__setattr__(config, "deck_port", int(getattr(args, "deck_port", 8765)))
            # force live capture stack
            from dataclasses import replace as _rep_play

            try:
                config = _rep_play(config, enable_ws=True)
            except Exception:
                pass
            # outcome live
            try:
                object.__setattr__(config.outcome, "enabled", True)
            except Exception:
                try:
                    config = _rep_play(
                        config,
                        outcome=_rep_play(
                            config.outcome,
                            enabled=True,
                            game_profile=getattr(args, "game_profile", config.outcome.game_profile),
                        ),
                    )
                except Exception:
                    pass
            # visual live — LOCAL ONNX/heuristic only, never mock/cloud fallback
            try:
                _gp = getattr(args, "game_profile", None) or getattr(
                    config.outcome, "game_profile", None
                )
                config = _rep_play(
                    config,
                    visual=_rep_play(
                        config.visual,
                        enabled=True,
                        prefer_local=True,
                        local_fallback=True,
                        frame_sample_rate=getattr(
                            args, "visual_sample_rate", config.visual.frame_sample_rate
                        ),
                        game_profile=_gp,
                    ),
                )
            except Exception:
                try:
                    object.__setattr__(config.visual, "enabled", True)
                    object.__setattr__(config.visual, "prefer_local", True)
                except Exception:
                    pass
            # HDMI / UVC capture card (PS5) — primary frame source for --play
            try:
                # Capture at 60 Hz under --play so Deck LIVE / clip ring run full-rate.
                # Override with --streamer-fps N if needed.
                _sfps = float(getattr(args, "streamer_fps", 30.0) or 30.0)
                _explicit_sfps = False
                try:
                    import sys as _sys_sfps

                    _explicit_sfps = any(
                        a == "--streamer-fps" or a.startswith("--streamer-fps=")
                        for a in _sys_sfps.argv
                    )
                except Exception:
                    pass
                if not _explicit_sfps:
                    _sfps = 60.0
                _dev = int(getattr(args, "streamer_device", -1))
                # Auto-resolve physical card when -1 or when index would hit a webcam
                try:
                    from qoresence.lobes.streamer import resolve_capture_device

                    _resolved = resolve_capture_device(
                        None if _dev < 0 else _dev,
                        prefer_name="USB3.0 Video",
                        allow_obs_vcam=False,
                    )
                    if _resolved is not None:
                        _dev, _dev_name = _resolved
                        log.info(
                            "play capture auto-resolve: idx=%s name=%r (survives unplug/replug)",
                            _dev,
                            _dev_name,
                        )
                    elif _dev < 0:
                        log.warning(
                            "play capture: no physical card listed yet — will hotplug-rebind on plug"
                        )
                        _dev = -1
                except Exception as _re:
                    log.debug("capture resolve: %s", _re)
                config = _rep_play(
                    config,
                    streamer=_rep_play(
                        config.streamer,
                        enabled=True,
                        device_index=_dev,
                        device_name="USB3.0 Video",
                        backend=str(getattr(args, "streamer_backend", "dshow") or "dshow"),
                        width=int(getattr(args, "streamer_width", 1280) or 1280),
                        height=int(getattr(args, "streamer_height", 720) or 720),
                        fps_target=_sfps,
                    ),
                )
                log.info(
                    "play frame source: streamer %s idx=%s (%sx%s @ %.0ffps) — HDMI/UVC auto-name; "
                    "LIVE ring @ 60; list: python -m qoresence.cli --streamer-list",
                    getattr(args, "streamer_backend", "dshow"),
                    _dev,
                    getattr(args, "streamer_width", 1280),
                    getattr(args, "streamer_height", 720),
                    _sfps,
                )
            except Exception:
                try:
                    object.__setattr__(config.streamer, "enabled", True)
                except Exception:
                    pass
            # controller lobe — always wait in --play so a late DualSense plug-in
            # still feeds InputRing / IVC without requiring --controller at boot
            if not getattr(args, "controller", False):
                try:
                    config = _rep_play(
                        config,
                        controller=_rep_play(
                            config.controller,
                            enabled=True,
                            poll_rate_hz=float(getattr(args, "controller_rate", 1000.0)),
                        ),
                    )
                    log.info("play: controller lobe waiting for DualSense (USB/BT hot-plug)")
                except Exception as _e:
                    log.debug("play controller enable skipped: %s", _e)
            # mss desktop only when user explicitly asked (--screen). Desktop frames
            # make LocalVLM guess football from wallpaper green while OCR crop is empty.
            if getattr(args, "screen", False):
                try:
                    config = _rep_play(
                        config,
                        screen=_rep_play(
                            config.screen,
                            enabled=True,
                            fps_target=min(float(getattr(args, "screen_fps", 5.0) or 5.0), 6.0),
                        ),
                    )
                    log.info(
                        "play also enabled --screen (mss monitor); visual still prefers streamer if both run"
                    )
                except Exception:
                    try:
                        object.__setattr__(config.screen, "enabled", True)
                    except Exception:
                        pass
            # clutchbot live — deck_feed backend always; Twitch if channel+token set
            try:
                from pathlib import Path as _P_play

                from qoresence.core import TwitchConfig as _TwPlay

                _ch = (getattr(args, "clutchbot_channel", "") or "").strip()
                _user = (getattr(args, "clutchbot_username", "") or "").strip()
                _tok = getattr(args, "clutchbot_token", None)
                _tok_file = getattr(args, "clutchbot_token_file", None)
                if not _tok_file and _P_play(".secrets/twitch_oauth.txt").exists():
                    _tok_file = ".secrets/twitch_oauth.txt"
                if not _ch:
                    import os as _os_tw

                    _ch = (
                        _os_tw.environ.get("QORESENCE_TWITCH_CHANNEL")
                        or _os_tw.environ.get("QORESENCE_CLUTCHBOT_CHANNEL")
                        or ""
                    ).strip()
                    _user = (
                        _user
                        or (
                            _os_tw.environ.get("QORESENCE_TWITCH_BOT_USERNAME")
                            or _os_tw.environ.get("QORESENCE_CLUTCHBOT_USERNAME")
                            or _ch
                        ).strip()
                    )
                    _tok = _tok or _os_tw.environ.get("QORESENCE_TWITCH_OAUTH_TOKEN")
                    _tok_file = _tok_file or _os_tw.environ.get("QORESENCE_TWITCH_TOKEN_FILE")
                _tw_ok = bool(_ch and (_user or _ch) and (_tok or _tok_file))
                _tw = _TwPlay(
                    enabled=_tw_ok,
                    channel=_ch,
                    bot_username=_user or _ch,
                    oauth_token=_tok,
                    token_file=_tok_file,
                    helix_token=getattr(args, "clutchbot_helix_token", None),
                    helix_token_file=getattr(args, "clutchbot_helix_token_file", None),
                    client_id=getattr(args, "clutchbot_client_id", None),
                    client_secret=getattr(args, "clutchbot_client_secret", None),
                    broadcaster_id=getattr(args, "clutchbot_broadcaster_id", None),
                    broadcaster_username=getattr(args, "clutchbot_broadcaster_username", None)
                    or _ch
                    or None,
                    message_interval_s=float(getattr(args, "clutchbot_interval", 2.0) or 2.0),
                    enable_clips=bool(getattr(args, "clutchbot_enable_clips", False)),
                    enable_predictions=bool(getattr(args, "clutchbot_enable_predictions", False)),
                    enable_follow_alerts=bool(
                        getattr(args, "clutchbot_enable_follow_alerts", False)
                    ),
                    enable_sub_alerts=bool(getattr(args, "clutchbot_enable_sub_alerts", False)),
                    enable_redemption_alerts=bool(
                        getattr(args, "clutchbot_enable_redemption_alerts", False)
                    ),
                )
                _llm_key = ".secrets/quicksilver_clutchbot.key"
                _llm_on = _P_play(_llm_key).exists() or bool(
                    getattr(config.clutchbot, "llm_api_key", None)
                    or getattr(config.clutchbot, "llm_api_key_file", None)
                )
                config = _rep_play(
                    config,
                    clutchbot=_rep_play(
                        config.clutchbot,
                        enabled=True,
                        enable_chat=not bool(getattr(args, "clutchbot_no_chat", False)),
                        twitch=_tw,
                        deck_enabled=True,
                        deck_host=getattr(args, "deck_host", "127.0.0.1"),
                        deck_port=int(getattr(args, "deck_port", 8765) or 8765),
                        llm_enabled=_llm_on
                        or bool(getattr(config.clutchbot, "llm_enabled", False)),
                        llm_api_key_file=(
                            getattr(config.clutchbot, "llm_api_key_file", None)
                            or (_llm_key if _P_play(_llm_key).exists() else None)
                        ),
                        a2a_enabled=bool(
                            getattr(args, "a2a", False)
                            or getattr(config.clutchbot, "a2a_enabled", False)
                        ),
                    ),
                )
                log.info(
                    "play ClutchBot: deck_feed=on twitch=%s llm=%s a2a=%s",
                    "on" if _tw_ok else "off (add channel+token for IRC)",
                    "on" if _llm_on else "off",
                    "on" if getattr(args, "a2a", False) else "off",
                )
            except Exception as _cb_e:
                log.warning("play ClutchBot wiring partial: %s", _cb_e)
                try:
                    object.__setattr__(config.clutchbot, "enabled", True)
                except Exception:
                    pass
            # Allow scoreboard OCR under heuristic when ONNX is absent (live play).
            # Tests set QORESENCE_DISABLE_SCOREBOARD_OCR=1 in conftest.
            try:
                import os as _os_play

                _os_play.environ.pop("QORESENCE_DISABLE_SCOREBOARD_OCR", None)
            except Exception:
                pass
        except Exception:
            pass

    if getattr(args, "society_audit", False) and not getattr(args, "play", False):
        from qoresence.agents.society import run_audit_once

        rec = run_audit_once()
        print(rec.text if rec else "no audit")  # noqa: T201
        sys.exit(0)
    if getattr(args, "society_propose_cuts", False) and not getattr(args, "play", False):
        from qoresence.agents.society import run_propose_cuts_once

        rec = run_propose_cuts_once()
        print(rec.text if rec else "no proposal")  # noqa: T201
        sys.exit(0)

    # Ghost Cut one-shot post-session
    _is_reel_one_shot = bool(
        getattr(args, "foundry_reel", False)
        or getattr(args, "render_reels", False)
        or getattr(args, "foundry_reel_clip", None)
    )
    if _is_reel_one_shot and not getattr(args, "play", False) and not getattr(args, "deck", False):
        try:
            from qoresence.studio.render_command import render_reels

            if getattr(args, "foundry_reel_no_wait", False):
                log.warning(
                    "Ghost Cut one-shot always waits; use --play --deck --studio "
                    "to queue in the background"
                )
            _jobs = render_reels(
                config,
                clip_path=args.foundry_reel_clip,
                count=args.foundry_reel_count,
                output_dir=args.foundry_reel_output_dir,
                kinds=args.foundry_reel_kinds,
                wait=True,
            )
            _ok = sum(1 for j in _jobs if j and j.status == "completed")
            _fail = sum(1 for j in _jobs if j and j.status == "failed")
            _pending = sum(1 for j in _jobs if j and j.status not in {"completed", "failed"})
            print(f"Ghost Cut: completed={_ok} failed={_fail} pending={_pending}")  # noqa: T201
            sys.exit(0 if _ok or _pending else 1)
        except Exception as e:
            log.exception("Ghost Cut failed: %s", e)
            sys.exit(1)

    if getattr(args, "deck", False) or (
        getattr(args, "studio", False) and not _is_reel_one_shot
    ):
        try:
            object.__setattr__(config, "deck_enabled", True)
            object.__setattr__(config, "deck_host", getattr(args, "deck_host", "127.0.0.1"))
            object.__setattr__(config, "deck_port", int(getattr(args, "deck_port", 8765)))
        except Exception:
            pass

    # Validate
    try:
        config.validate()
    except ValueError as e:
        log.error("Config validation failed: %s", e)
        sys.exit(1)

    # Create app
    app = QoresenceApp(config, trio_config)
    app.initialize_lobes()
    app.connect_lobes()

    if args.dry_run:
        log.info("Dry run complete - config valid, lobes initialized")
        return

    if args.health_check:
        checks = run_health_checks(app)
        import json

        print(json.dumps(checks, indent=2))  # noqa: T201
        sys.exit(0 if checks["overall"] == "healthy" else 1)

    # Start
    if not app.start():
        log.error("Failed to start")
        sys.exit(1)

    # Optional native Retina Monitor (in-process FrameHub ← streamer; default OFF)
    _monitor_stop = None
    if getattr(args, "monitor", False):
        try:
            from qoresence.monitor.window import start_monitor_thread

            deck_port = int(getattr(args, "deck_port", 8765) or 8765)
            _mon_t, _monitor_stop = start_monitor_thread(
                max_width=int(getattr(args, "monitor_max_width", 1280) or 1280),
                situation_url=f"http://127.0.0.1:{deck_port}/api/situation",
                target_hz=30.0,
                preset=str(getattr(args, "monitor_preset", "full") or "full"),
            )
            log.info(
                "Retina Monitor on (FrameHub ← streamer; no second capture) thread=%s",
                _mon_t.name,
            )
        except Exception as e:
            log.error(
                "Retina Monitor failed to start: %s. "
                "Install opencv (pip install 'qoresence[monitor]'). "
                "Play/Deck continue without the window.",
                e,
            )

    # Optional system tray icon (default OFF)
    _tray_stop = None
    if getattr(args, "tray", False):
        try:
            from qoresence.ui.tray import start_tray

            deck_port = int(getattr(args, "deck_port", 8765) or 8765)
            _tray_t, _tray_stop = start_tray(
                port=deck_port,
                on_stop=app.signal_shutdown,
            )
            log.info("System tray icon started (port=%s)", deck_port)
        except ImportError:
            log.info(
                "System tray requires pystray. "
                "Install: pip install pystray. Continuing without tray."
            )
        except Exception as e:
            log.debug("Tray failed to start: %s", e)

    # Signal handling
    def signal_handler(signum, frame):
        log.info("Received signal %s, shutting down...", signum)
        app.signal_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Wait for shutdown
    try:
        app.wait_for_shutdown()
    except KeyboardInterrupt:
        pass

    if _monitor_stop is not None:
        try:
            _monitor_stop.set()
        except Exception:
            pass

    if _tray_stop is not None:
        try:
            _tray_stop.set()
        except Exception:
            pass

    app.stop()
    log.info("Goodbye")


if __name__ == "__main__":
    main()
