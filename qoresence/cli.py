"""
Qoresence CLI — Phase 9 Production Entry Point

Unified command-line interface for running Qoresence lobes.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from qoresence.agents import ClutchBotAgent
from qoresence.core import (
    RetinaEventBus,
    RetinaUnifiedConfig,
    SessionAuthority,
    TwitchConfig,
    clock_ns,
)
from qoresence.fusion import PresenceFusionEngine, create_fusion_engine
from qoresence.game_detection import GameAutoDetector
from qoresence.lobes import (
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


# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ──────────────────────────────────────────────────────────────────────────────

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
        self.bus = RetinaEventBus(
            session_id=self.identity.session_id,
            jsonl_path=Path(config.jsonl_path) if config.jsonl_path else None,
            enable_ws=config.enable_ws,
            ws_host=config.ws_host,
            ws_port=config.ws_port,
            # Trio-retina
            trio_config=self.trio_config,
            session_identity=self.identity,
            visual_oracle_root_provider=None,  # Will be set after visual init
            posp_root_provider=None,  # Will be set after outcome init
            first_session_id=self.identity.session_id,  # Use current as first for now
            device_key=None,  # TODO: load from config
        )

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
                learning_path=Path(self.config.game_detection.learning_path) if self.config.game_detection.learning_path else None,
                ocr_provider=self.config.game_detection.ocr_provider,
                model_dir=Path(self.config.game_detection.vision_model_dir) if self.config.game_detection.vision_model_dir else None,
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
        # Screen ← Controller (for coupling)
        if self.screen and self.controller:
            def controller_provider():
                # Return recent trigger/stick state as feature vector
                stats = self.controller.get_stats()
                return [stats.get('last_trigger', 0.0), stats.get('stick_motion', 0.0)]
            self.screen.set_controller_provider(controller_provider)

        # Visual ← Streamer/Screen (for frame provider)
        if self.visual:
            if self.streamer:
                def frame_provider():
                    return self.streamer.get_current_frame()
                self.visual.set_frame_provider(frame_provider)
            elif self.screen:
                def frame_provider():
                    return self.screen.get_current_frame()
                self.visual.set_frame_provider(frame_provider)

            # Visual ← Outcome/Controller/Screen (for cross-modal)
            def modality_provider():
                modalities = {}
                if self.outcome:
                    modalities['outcome'] = self.outcome.get_last_state()
                if self.controller:
                    modalities['controller'] = self.controller.get_stats()
                if self.screen:
                    modalities['screen'] = {'coupling_score': 0.0}  # Would need screen coupling access
                return modalities
            self.visual.set_modality_provider(modality_provider)

        # Game detector ← Streamer/Screen (frames) and → Outcome (profile switch)
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

        # Fusion ← All lobes (lobe status updates)
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
                    if state and state.get('last_event'):
                        import hashlib
                        state_str = f"{state['last_event']}:{state.get('home_score',0)}:{state.get('away_score',0)}"
                        return hashlib.sha256(state_str.encode()).hexdigest()
                    return "c" * 64  # mock fallback
                self.bus._posp_root_provider = posp_root_provider

    def start(self) -> bool:
        """Start all enabled lobes."""
        if self._running:
            log.warning("Already running")
            return True

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
            log.error("Failed to start controller")
            return False

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
        return True

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

        if self.controller:
            self.controller.stop()

        if self.streamer:
            self.streamer.stop()

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


# ──────────────────────────────────────────────────────────────────────────────
# HEALTH CHECKS
# ──────────────────────────────────────────────────────────────────────────────

def run_health_checks(app: QoresenceApp) -> dict:
    """Run health checks on all components."""
    checks = {
        "timestamp_ns": clock_ns(),
        "session_id": app.identity.session_id,
        "overall": "healthy",
        "components": {},
    }

    # Check event bus
    bus_stats = (app.bus.stats() if hasattr(app.bus, "stats") else app.bus.get_stats())  # type: ignore
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
    for comp, info in checks["components"].items():
        if info["status"] != "healthy":
            checks["overall"] = "degraded"
            break

    return checks


# ──────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


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
        config.visual = replace(config.visual, enabled=True, frame_sample_rate=args.visual_sample_rate)
        config.game_detection = replace(config.game_detection, enabled=getattr(args, "game_detect", True))

    if getattr(args, "game_detect", False):
        config.game_detection = replace(config.game_detection, enabled=True)
    if getattr(args, "no_game_detect", False):
        config.game_detection = replace(config.game_detection, enabled=False)

    # Game detection tuning
    config.game_detection = replace(
        config.game_detection,
        confidence_threshold=getattr(args, "game_detect_confidence", config.game_detection.confidence_threshold),
        stability_count=getattr(args, "game_detect_stability", config.game_detection.stability_count),
        poll_interval_s=getattr(args, "game_detect_poll", config.game_detection.poll_interval_s),
    )

    # Enable lobes based on flags
    if args.streamer:
        config.streamer = replace(config.streamer, enabled=True, capture_fps=args.streamer_fps)
    if args.controller:
        config.controller = replace(config.controller, enabled=True, poll_rate_hz=args.controller_rate)
    if args.outcome:
        config.outcome = replace(config.outcome, enabled=True, game_profile=args.game_profile)
    if args.screen:
        config.screen = replace(config.screen, enabled=True, fps_target=args.screen_fps)
    if args.visual:
        config.visual = replace(config.visual, enabled=True, frame_sample_rate=args.visual_sample_rate)

    # ClutchBot agent (explicit or via --stream preset)
    if args.clutchbot or args.stream:
        config.clutchbot = replace(
            config.clutchbot,
            enabled=True,
            enable_chat=not args.clutchbot_no_chat,
            clip_has_delay=not args.clutchbot_no_clip_delay,
            twitch=TwitchConfig(
                enabled=args.clutchbot_channel != "",
                channel=args.clutchbot_channel,
                bot_username=args.clutchbot_username,
                oauth_token=args.clutchbot_token,
                token_file=args.clutchbot_token_file,
                helix_token=args.clutchbot_helix_token,
                helix_token_file=args.clutchbot_helix_token_file,
                client_id=args.clutchbot_client_id,
                client_secret=args.clutchbot_client_secret,
                broadcaster_id=args.clutchbot_broadcaster_id,
                broadcaster_username=args.clutchbot_broadcaster_username,
                message_interval_s=args.clutchbot_interval,
                enable_clips=args.clutchbot_enable_clips,
                enable_predictions=args.clutchbot_enable_predictions,
                enable_follow_alerts=args.clutchbot_enable_follow_alerts,
                enable_sub_alerts=args.clutchbot_enable_sub_alerts,
                enable_redemption_alerts=args.clutchbot_enable_redemption_alerts,
            ),
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
    parser.add_argument("--streamer-fps", type=float, default=30.0, help="Streamer capture FPS")
    parser.add_argument("--controller", action="store_true", help="Enable controller lobe (HID)")
    parser.add_argument("--controller-rate", type=float, default=1000.0, help="Controller poll rate (Hz)")
    parser.add_argument("--outcome", action="store_true", help="Enable outcome lobe (game events)")
    parser.add_argument(
        "--game-profile",
        choices=[
            "ncaa_football_27", "call_of_duty",
            "madden_27", "madden_2027", "ncaa_27", "college_football_27",
            "ea_sports_college_football_27", "cod", "modern_warfare", "warzone",
        ],
        default="ncaa_football_27",
        help="Game profile (supports common aliases)",
    )
    parser.add_argument("--screen", action="store_true", help="Enable screen lobe (mss/DXGI)")
    parser.add_argument("--screen-fps", type=float, default=60.0, help="Screen capture FPS")
    parser.add_argument("--visual", action="store_true", help="Enable visual lobe (VLM)")
    parser.add_argument("--visual-sample-rate", type=int, default=30, help="Visual frame sample rate")

    # Game detection (rich visual context for outcome/clutchbot)
    parser.add_argument("--game-detect", action="store_true", help="Enable game auto-detection (enabled by --stream)")
    parser.add_argument("--no-game-detect", action="store_true", help="Disable game auto-detection even in --stream")
    parser.add_argument("--game-detect-confidence", type=float, default=0.65, help="Game detection confidence threshold")
    parser.add_argument("--game-detect-stability", type=int, default=2, help="Consecutive detections required")
    parser.add_argument("--game-detect-poll", type=float, default=3.0, help="Game detection poll interval (s)")

    # ClutchBot (Twitch agent)
    parser.add_argument("--clutchbot", action="store_true", help="Enable ClutchBot Twitch agent")
    parser.add_argument("--clutchbot-channel", default="", help="Twitch channel for the bot to join (no #)")
    parser.add_argument("--clutchbot-username", default="", help="Twitch bot username")
    parser.add_argument("--clutchbot-token", default=None, help="Twitch bot OAuth token")
    parser.add_argument("--clutchbot-token-file", default=None, help="File containing the Twitch bot OAuth token")
    parser.add_argument("--clutchbot-helix-token", default=None, help="Twitch Helix access token (for clips/predictions)")
    parser.add_argument("--clutchbot-helix-token-file", default=None, help="File containing the Twitch Helix token")
    parser.add_argument("--clutchbot-client-id", default=None, help="Twitch application Client ID")
    parser.add_argument("--clutchbot-client-secret", default=None, help="Twitch application Client Secret")
    parser.add_argument("--clutchbot-broadcaster-id", default=None, help="Twitch broadcaster user ID")
    parser.add_argument("--clutchbot-broadcaster-username", default=None, help="Twitch broadcaster login name")
    parser.add_argument("--clutchbot-interval", type=float, default=2.0, help="Minimum seconds between sent IRC messages")
    parser.add_argument("--clutchbot-no-chat", action="store_true", help="Disable chat/greeting actions")
    parser.add_argument("--clutchbot-enable-clips", action="store_true", help="Create clips on clutch moments")
    parser.add_argument("--clutchbot-no-clip-delay", action="store_true", help="Disable delay when creating clips (default: has delay)")
    parser.add_argument("--clutchbot-enable-predictions", action="store_true", help="Start channel-point predictions")
    parser.add_argument("--clutchbot-enable-follow-alerts", action="store_true", help="EventSub follow alerts")
    parser.add_argument("--clutchbot-enable-sub-alerts", action="store_true", help="EventSub subscription alerts")
    parser.add_argument("--clutchbot-enable-redemption-alerts", action="store_true", help="EventSub redemption alerts")

    # Trio-retina (w3bstream validation)
    parser.add_argument("--trio", action="store_true", help="Enable trio-retina w3bstream validation")
    parser.add_argument("--trio-wasm-path", default="w3bstream_applet.wasm", help="Path to w3bstream applet WASM")
    parser.add_argument("--trio-validate-on-ingest", action="store_true", help="Validate each event at ingestion")
    parser.add_argument("--trio-validate-on-flush", action="store_true", default=True, help="Validate batched events periodically")
    parser.add_argument("--trio-flush-interval", type=float, default=30.0, help="Batch flush interval (seconds)")
    parser.add_argument("--trio-block-rpc", default="https://babel-api.testnet.iotex.io", help="IoTeX RPC for block number")
    parser.add_argument("--trio-node-session-verify", action="store_true", help="Enable DEPIN-1 LEG 2 node/session gate")
    parser.add_argument("--trio-events-root-verify", action="store_true", help="Verify events root (merkle)")

    # Options
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--health-check", action="store_true", help="Run health checks and exit")
    parser.add_argument("--dry-run", action="store_true", help="Initialize but don't start lobes")

    args = parser.parse_args()

    setup_logging(args.log_level)

    # Create trio-retina config (CLI args take precedence over env vars)
    trio_config = None
    trio_enabled = args.trio or os.environ.get("QORESENCE_TRIO_ENABLED", "0") == "1"
    if TRIO_AVAILABLE and trio_enabled:
        trio_config = TrioRetinaConfig(
            enabled=True,
            wasm_path=args.trio_wasm_path or os.environ.get("QORESENCE_TRIO_WASM_PATH", "w3bstream_applet.wasm"),
            validate_on_ingest=args.trio_validate_on_ingest or os.environ.get("QORESENCE_TRIO_VALIDATE_ON_INGEST", "0") == "1",
            validate_on_flush=args.trio_validate_on_flush or os.environ.get("QORESENCE_TRIO_VALIDATE_ON_FLUSH", "1") == "1",
            flush_interval_s=float(args.trio_flush_interval or os.environ.get("QORESENCE_TRIO_FLUSH_INTERVAL", "30.0")),
            block_rpc_url=args.trio_block_rpc or os.environ.get("QORESENCE_TRIO_BLOCK_RPC", "https://babel-api.testnet.iotex.io"),
            node_session_verify=args.trio_node_session_verify or os.environ.get("QORESENCE_TRIO_NODE_SESSION_VERIFY", "0") == "1",
            retina_events_root_verify=args.trio_events_root_verify or os.environ.get("QORESENCE_TRIO_EVENTS_ROOT_VERIFY", "0") == "1",
        )
        log.info("Trio-retina validation enabled")

    # Create config
    config = create_config_from_args(args)

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
        print(json.dumps(checks, indent=2))
        sys.exit(0 if checks["overall"] == "healthy" else 1)

    # Start
    if not app.start():
        log.error("Failed to start")
        sys.exit(1)

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

    app.stop()
    log.info("Goodbye")


if __name__ == "__main__":
    main()
