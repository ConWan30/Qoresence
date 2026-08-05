"""
Qoresence CLI — Phase 9 Production Entry Point

Unified command-line interface for running Qoresence lobes.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from qoresence.core import (
    RetinaUnifiedConfig,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
    clock_ns,
)
from qoresence.lobes import (
    StreamerRuntime,
    ControllerRuntime,
    OutcomeRuntime,
    ScreenRuntime,
    VisualRuntime,
)
from qoresence.fusion import PresenceFusionEngine, FusionWeights, create_fusion_engine

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ──────────────────────────────────────────────────────────────────────────────

class QoresenceApp:
    """Main application coordinator."""

    def __init__(self, config: RetinaUnifiedConfig):
        self.config = config
        self.identity = SessionAuthority.mint(
            session_id=config.session_id,
            device_id=config.device_id,
            session_head_ns=config.session_head_ns,
        )

        # Event bus
        self.bus = RetinaEventBus(
            session_id=self.identity.session_id,
            jsonl_path=Path(config.jsonl_path) if config.jsonl_path else None,
            enable_ws=config.enable_ws,
            ws_host=config.ws_host,
            ws_port=config.ws_port,
        )

        # Lobe runtimes
        self.streamer: Optional[StreamerRuntime] = None
        self.controller: Optional[ControllerRuntime] = None
        self.outcome: Optional[OutcomeRuntime] = None
        self.screen: Optional[ScreenRuntime] = None
        self.visual: Optional[VisualRuntime] = None
        self.fusion: Optional[PresenceFusionEngine] = None

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

        # Fusion engine (always created for presence reports)
        self.fusion = create_fusion_engine(
            config=self.config,
            bus=self.bus,
            session_head_ns=self.identity.session_head_ns,
        )
        log.info("Presence Fusion Engine initialized")

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

    def start(self) -> bool:
        """Start all enabled lobes."""
        if self._running:
            log.warning("Already running")
            return True

        self._running = True
        self._start_time = time.time()

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

        if self.fusion:
            self.fusion.start()

        log.info("Qoresence started: session=%s", self.identity.session_id)
        return True

    def stop(self) -> None:
        """Stop all lobes gracefully."""
        if not self._running:
            return

        self._running = False
        log.info("Shutting down...")

        if self.fusion:
            self.fusion.stop()

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
        return {
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
            "bus_stats": self.bus.get_stats(),
        }


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
    bus_stats = app.bus.get_stats()
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
    # This would use the unified config factory
    # For now, create minimal config
    config = RetinaUnifiedConfig(
        session_id=args.session_id or "",
        session_head_ns=args.session_head_ns or 0,
        device_id=args.device_id or "",
        jsonl_path=args.jsonl_path or "",
        enable_ws=args.enable_ws,
        ws_host=args.ws_host,
        ws_port=args.ws_port,
    )

    # Enable lobes based on flags
    if args.streamer:
        config.streamer.enabled = True
        config.streamer.capture_fps = args.streamer_fps
    if args.controller:
        config.controller.enabled = True
        config.controller.poll_rate_hz = args.controller_rate
    if args.outcome:
        config.outcome.enabled = True
        config.outcome.game_profile = args.game_profile
    if args.screen:
        config.screen.enabled = True
        config.screen.fps_target = args.screen_fps
    if args.visual:
        config.visual.enabled = True
        config.visual.frame_sample_rate = args.visual_sample_rate

    return config


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="qoresence",
        description="Qoresence - Gamer Presence Observation Plane",
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

    # Lobes
    parser.add_argument("--streamer", action="store_true", help="Enable streamer lobe (UVC/OBS)")
    parser.add_argument("--streamer-fps", type=float, default=30.0, help="Streamer capture FPS")
    parser.add_argument("--controller", action="store_true", help="Enable controller lobe (HID)")
    parser.add_argument("--controller-rate", type=float, default=1000.0, help="Controller poll rate (Hz)")
    parser.add_argument("--outcome", action="store_true", help="Enable outcome lobe (game events)")
    parser.add_argument("--game-profile", choices=["ncaa_football_27", "call_of_duty"], default="ncaa_football_27")
    parser.add_argument("--screen", action="store_true", help="Enable screen lobe (mss/DXGI)")
    parser.add_argument("--screen-fps", type=float, default=60.0, help="Screen capture FPS")
    parser.add_argument("--visual", action="store_true", help="Enable visual lobe (VLM)")
    parser.add_argument("--visual-sample-rate", type=int, default=30, help="Visual frame sample rate")

    # Options
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--health-check", action="store_true", help="Run health checks and exit")
    parser.add_argument("--dry-run", action="store_true", help="Initialize but don't start lobes")

    args = parser.parse_args()

    setup_logging(args.log_level)

    # Create config
    config = create_config_from_args(args)

    # Validate
    try:
        config.validate()
    except ValueError as e:
        log.error("Config validation failed: %s", e)
        sys.exit(1)

    # Create app
    app = QoresenceApp(config)
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