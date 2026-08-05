#!/usr/bin/env python3
"""
Qoresence Real-World Integration Test — Phase 10

Tests the full observation pipeline with actual hardware:
- DualShock Edge controller (HID)
- Capture card / OBS Virtual Camera (UVC)
- Screen capture (mss/DXGI)
- Game profile detection (NCAA 27 / CoD)
- Presence fusion engine

Run with: python scripts/integration_test.py [--dry-run] [--duration SECONDS]
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import asyncio
import time
from pathlib import Path
from typing import Optional

# Add qoresence to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qoresence.core import (
    RetinaUnifiedConfig,
    RetinaEventBus,
    SessionAuthority,
    StreamerConfig,
    ControllerConfig,
    ScreenConfig,
    OutcomeConfig,
    VisualConfig,
    FusionWeights,
    SourceLobe,
)
from qoresence.lobes import (
    StreamerRuntime,
    ControllerRuntime,
    ScreenRuntime,
    OutcomeRuntime,
    VisualRuntime,
    list_controllers,
    list_monitors,
)
from qoresence.fusion import PresenceFusionEngine, create_fusion_engine

try:
    from qoresence.trio import TrioRetinaConfig
    TRIO_AVAILABLE = True
except ImportError:
    TrioRetinaConfig = None  # type: ignore
    TRIO_AVAILABLE = False

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# HARDWARE DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def detect_dualshock_edge() -> Optional[dict]:
    """Detect DualShock Edge controller via HID."""
    try:
        import hid
        devices = hid.enumerate()
        for d in devices:
            if d['vendor_id'] == 0x054C and d['product_id'] == 0x0CE6:
                return {
                    'vendor_id': d['vendor_id'],
                    'product_id': d['product_id'],
                    'path': d['path'],
                    'manufacturer': d.get('manufacturer_string', ''),
                    'product': d.get('product_string', ''),
                    'serial': d.get('serial_number', ''),
                }
    except Exception as e:
        log.warning(f"HID enumeration failed: {e}")
    return None


def detect_capture_devices() -> list[dict]:
    """Detect available video capture devices."""
    devices = []
    try:
        import cv2
        # Test first 5 indices
        for i in range(5):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                # Try to read a frame
                ok, frame = cap.read()
                if ok and frame is not None:
                    h, w = frame.shape[:2]
                    devices.append({
                        'index': i,
                        'width': w,
                        'height': h,
                        'backend': 'dshow',
                    })
                cap.release()
    except Exception as e:
        log.warning(f"Capture device detection failed: {e}")
    return devices


def detect_monitors() -> list[dict]:
    """Detect available monitors for screen capture."""
    try:
        return list_monitors()
    except Exception as e:
        log.warning(f"Monitor detection failed: {e}")
        return []


def detect_game_window() -> Optional[str]:
    """Try to detect NCAA 27 or CoD game window."""
    try:
        import win32gui
        windows = []
        def enum_handler(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows.append(title)
        win32gui.EnumWindows(enum_handler, None)

        for title in windows:
            title_lower = title.lower()
            if any(kw in title_lower for kw in ['ncaa', 'college football', 'football 27']):
                return f"NCAA 27: {title}"
            if any(kw in title_lower for kw in ['call of duty', 'warzone', 'modern warfare', 'black ops']):
                return f"Call of Duty: {title}"
    except ImportError:
        log.warning("win32gui not available for window detection")
    except Exception as e:
        log.warning(f"Window detection failed: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# INTEGRATION TEST APP
# ──────────────────────────────────────────────────────────────────────────────

class IntegrationTestApp:
    """Full pipeline integration test."""

    def __init__(
        self,
        config: RetinaUnifiedConfig,
        duration_s: float = 30.0,
        trio_config: Optional["TrioRetinaConfig"] = None,
    ):
        self.config = config
        self.duration_s = duration_s
        self.trio_config = trio_config
        self.identity = SessionAuthority.mint(
            session_id=config.session_id,
            device_id_hex=config.device_id_hex,
            session_head_ns=config.session_head_ns,
        )

        # Event bus with JSONL output and optional trio-retina validation
        self.bus = RetinaEventBus(
            session_id=self.identity.session_id,
            jsonl_path=Path(config.jsonl_path) if config.jsonl_path else None,
            enable_ws=config.enable_ws,
            ws_host=config.ws_host,
            ws_port=config.ws_port,
            trio_config=trio_config,
            session_identity=self.identity,
            first_session_id=self.identity.session_id,
        )

        # Lobe runtimes
        self.streamer: Optional[StreamerRuntime] = None
        self.controller: Optional[ControllerRuntime] = None
        self.screen: Optional[ScreenRuntime] = None
        self.outcome: Optional[OutcomeRuntime] = None
        self.visual: Optional[VisualRuntime] = None
        self.fusion: Optional[PresenceFusionEngine] = None

        self._running = False
        self._start_time = 0.0
        self._stats = {
            'events_received': 0,
            'lobe_events': {},
            'anomalies_detected': 0,
            'presence_reports': 0,
        }

    def initialize(self) -> bool:
        """Initialize all enabled lobes."""
        log.info("Initializing lobes...")

        # Streamer
        if self.config.streamer.enabled:
            self.streamer = StreamerRuntime(
                config=self.config.streamer,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("  OK Streamer lobe initialized")

        # Controller
        if self.config.controller.enabled:
            self.controller = ControllerRuntime(
                config=self.config.controller,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("  OK Controller lobe initialized")

        # Screen
        if self.config.screen.enabled:
            self.screen = ScreenRuntime(
                config=self.config.screen,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("  OK Screen lobe initialized")

        # Outcome
        if self.config.outcome.enabled:
            self.outcome = OutcomeRuntime(
                config=self.config.outcome,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("  OK Outcome lobe initialized")

        # Visual
        if self.config.visual.enabled:
            self.visual = VisualRuntime(
                config=self.config.visual,
                bus=self.bus,
                session_head_ns=self.identity.session_head_ns,
            )
            log.info("  OK Visual lobe initialized")

        # Fusion engine
        self.fusion = create_fusion_engine(
            config=self.config,
            bus=self.bus,
        )
        log.info("  OK Fusion engine initialized")

        # Cross-lobe connections
        self._connect_lobes()
        return True

    def _connect_lobes(self) -> None:
        """Connect lobe outputs to each other."""
        # Screen ← Controller (coupling)
        if self.screen and self.controller:
            def controller_provider():
                stats = self.controller.get_stats()
                return [stats.get('last_trigger', 0.0), stats.get('stick_motion', 0.0)]
            self.screen.set_controller_provider(controller_provider)

        # Visual ← Streamer/Screen (frames)
        if self.visual:
            if self.streamer:
                self.visual.set_frame_provider(self.streamer.get_current_frame)
            elif self.screen:
                self.visual.set_frame_provider(self.screen.get_current_frame)

        # Outcome ← Streamer/Screen (frames)
        if self.outcome:
            if self.streamer:
                self.outcome.set_frame_provider(self.streamer.get_current_frame)
            elif self.screen:
                self.outcome.set_frame_provider(self.screen.get_current_frame)

        # Visual ← Outcome/Controller/Screen (cross-modal)
        if self.visual:
            def modality_provider():
                modalities = {}
                if self.outcome:
                    modalities['outcome'] = self.outcome.get_last_state()
                if self.controller:
                    modalities['controller'] = self.controller.get_stats()
                if self.screen:
                    modalities['screen'] = {'coupling_score': 0.0}
                return modalities
            self.visual.set_modality_provider(modality_provider)

        # Fusion ← All lobes (presence callbacks)
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

        # Subscribe to bus for stats
        def stats_callback(event):
            self._stats['events_received'] += 1
            lobe = event.source_lobe.value
            self._stats['lobe_events'][lobe] = self._stats['lobe_events'].get(lobe, 0) + 1
            if event.type.value == 'presence_report':
                self._stats['presence_reports'] += 1
                if event.payload.get('anomalies'):
                    self._stats['anomalies_detected'] += len(event.payload['anomalies'])

        self.bus.subscribe(stats_callback)

    def start(self) -> bool:
        """Start all lobes."""
        log.info("Starting lobes...")

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

        self.bus.start()
        self._running = True
        self._start_time = time.time()
        log.info(f"Integration test started: session={self.identity.session_id}")
        return True

    def stop(self) -> None:
        """Stop all lobes."""
        if not self._running:
            return

        self._running = False
        log.info("Stopping lobes...")

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

        # Gracefully stop trio validator if running
        if self.bus._trio_validator and self.bus._ws_loop and self.bus._ws_loop.is_running():
            try:
                fut = asyncio.run_coroutine_threadsafe(self.bus.stop_trio_validator(), self.bus._ws_loop)
                fut.result(timeout=5)
            except Exception as e:
                log.warning(f"Trio validator stop timed out or failed: {e}")

        self.bus.stop()
        elapsed = time.time() - self._start_time
        log.info(f"Integration test stopped after {elapsed:.1f}s")

    def run(self) -> dict:
        """Run the integration test for configured duration."""
        if not self.start():
            return {'success': False, 'error': 'Failed to start'}

        try:
            time.sleep(self.duration_s)
        except KeyboardInterrupt:
            log.info("Interrupted by user")
        finally:
            self.stop()

        return {
            'success': True,
            'session_id': self.identity.session_id,
            'duration_s': round(time.time() - self._start_time, 1),
            'stats': self._stats,
            'lobe_status': self._get_lobe_status(),
        }

    def _get_lobe_status(self) -> dict:
        return {
            'streamer': self.streamer.is_running() if self.streamer else 'disabled',
            'controller': self.controller.is_running() if self.controller else 'disabled',
            'screen': self.screen.is_running() if self.screen else 'disabled',
            'outcome': self.outcome.is_running() if self.outcome else 'disabled',
            'visual': self.visual.is_running() if self.visual else 'disabled',
            'fusion': self.fusion.is_running() if self.fusion else 'disabled',
        }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def create_test_config(args) -> RetinaUnifiedConfig:
    """Create config for integration test."""
    # Auto-generate session if not provided
    session_id = args.session_id or f"integration_{int(time.time())}"
    session_head_ns = args.session_head_ns or time.time_ns()
    device_id = args.device_id or ""

    # Detect hardware if not specified
    streamer_device = args.streamer_device
    if streamer_device is None and args.auto_detect:
        devices = detect_capture_devices()
        if devices:
            streamer_device = devices[0]['index']
            log.info(f"Auto-detected capture device: index {streamer_device}")

    controller_vid = args.controller_vid
    controller_pid = args.controller_pid
    if controller_vid is None and controller_pid is None and args.auto_detect:
        edge = detect_dualshock_edge()
        if edge:
            controller_vid = edge['vendor_id']
            controller_pid = edge['product_id']
            log.info(f"Auto-detected DualShock Edge: {edge}")

    screen_monitor = args.screen_monitor
    if screen_monitor is None and args.auto_detect:
        monitors = detect_monitors()
        if monitors:
            screen_monitor = monitors[0]['index']
            log.info(f"Auto-detected monitor: index {screen_monitor}")

    # Detect game window for outcome profile
    game_profile = args.game_profile
    if game_profile == "auto" and args.auto_detect:
        window = detect_game_window()
        if window:
            if "NCAA" in window:
                game_profile = "ncaa_football_27"
            elif "Call of Duty" in window:
                game_profile = "call_of_duty"
            log.info(f"Auto-detected game: {window}")
        else:
            game_profile = "ncaa_football_27"
            log.info("No game window detected; defaulting to ncaa_football_27")
    elif game_profile == "auto":
        game_profile = "ncaa_football_27"

    # Build lobe configs
    streamer_config = StreamerConfig(
        enabled=args.streamer,
        device_index=streamer_device or 0,
        fps_target=args.streamer_fps,
        source_kind=args.streamer_source,
        backend=args.streamer_backend,
        eye_check_required=True,
    )

    controller_config = ControllerConfig(
        enabled=args.controller,
        device_vid=controller_vid,
        device_pid=controller_pid,
        poll_rate_hz=args.controller_rate,
    )

    screen_config = ScreenConfig(
        enabled=args.screen,
        capture_method=args.screen_method,
        monitor_index=screen_monitor or 0,
        fps_target=args.screen_fps,
    )

    from qoresence.core import GameProfileId
    outcome_config = OutcomeConfig(
        enabled=args.outcome,
        game_profile=GameProfileId(game_profile),
        confidence_threshold=args.outcome_confidence,
        poll_interval_s=args.outcome_interval,
    )

    visual_config = VisualConfig(
        enabled=args.visual,
        api_key=args.visual_api_key,
        frame_sample_rate=args.visual_sample_rate,
        game_category="football" if game_profile == "ncaa_football_27" else "shooter",
    )

    config = RetinaUnifiedConfig(
        session_id=session_id,
        session_head_ns=session_head_ns,
        device_id_hex=device_id,
        jsonl_path=args.jsonl_path,
        enable_ws=args.enable_ws,
        ws_host=args.ws_host,
        ws_port=args.ws_port,
        streamer=streamer_config,
        controller=controller_config,
        screen=screen_config,
        outcome=outcome_config,
        visual=visual_config,
        fusion_weights=FusionWeights(
            streamer_presence_sync=0.25,
            controller_causal_density=0.25,
            screen_coupling_score=0.20,
            outcome_coherence=0.15,
            visual_confirmation=0.15,
        ),
    )

    return config


def print_hardware_info() -> None:
    """Print detected hardware information."""
    print("\n" + "="*60)
    print("HARDWARE DETECTION")
    print("="*60)

    # Controllers
    print("\nControllers:")
    controllers = list_controllers()
    if controllers:
        for c in controllers:
            print(f"  - {c['product']} (VID:0x{c['vid']:04X} PID:0x{c['pid']:04X})")
    else:
        print("  None detected")

    # Capture devices
    print("\nCapture Devices:")
    devices = detect_capture_devices()
    if devices:
        for d in devices:
            print(f"  - Index {d['index']}: {d['width']}x{d['height']} ({d['backend']})")
    else:
        print("  None detected")

    # Monitors
    print("\nMonitors:")
    monitors = detect_monitors()
    if monitors:
        for m in monitors:
            print(f"  - Index {m['index']}: {m['width']}x{m['height']} at ({m['left']},{m['top']})")
    else:
        print("  None detected")

    # Game window
    print("\nGame Window:")
    window = detect_game_window()
    if window:
        print(f"  - {window}")
    else:
        print("  None detected (or win32gui not available)")

    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        prog="integration_test",
        description="Qoresence Real-World Integration Test",
    )

    # Hardware detection
    parser.add_argument("--detect-only", action="store_true",
                        help="Only detect hardware and exit")
    parser.add_argument("--auto-detect", action="store_true",
                        help="Auto-detect hardware for config")

    # Session
    parser.add_argument("--session-id", help="Session ID")
    parser.add_argument("--session-head-ns", type=int, help="Session head timestamp (ns)")
    parser.add_argument("--device-id", help="Device ID (64-char hex)")

    # Streamer
    parser.add_argument("--streamer", action="store_true", help="Enable streamer lobe")
    parser.add_argument("--streamer-device", type=int, help="Capture device index")
    parser.add_argument("--streamer-fps", type=float, default=15.0, help="Streamer FPS")
    parser.add_argument("--streamer-source", choices=["uvc_card", "obs_virtual"], default="uvc_card")
    parser.add_argument("--streamer-backend", choices=["auto", "dshow", "msmf"], default="dshow", help="Capture backend")

    # Controller
    parser.add_argument("--controller", action="store_true", help="Enable controller lobe")
    parser.add_argument("--controller-vid", type=lambda x: int(x, 0), help="Controller VID (hex)")
    parser.add_argument("--controller-pid", type=lambda x: int(x, 0), help="Controller PID (hex)")
    parser.add_argument("--controller-rate", type=float, default=1000.0, help="Poll rate (Hz)")

    # Screen
    parser.add_argument("--screen", action="store_true", help="Enable screen lobe")
    parser.add_argument("--screen-monitor", type=int, help="Monitor index")
    parser.add_argument("--screen-method", choices=["wgc", "dxgi", "mss"], default="wgc")
    parser.add_argument("--screen-fps", type=float, default=60.0, help="Screen capture FPS")

    # Outcome
    parser.add_argument("--outcome", action="store_true", help="Enable outcome lobe")
    parser.add_argument("--game-profile", choices=["ncaa_football_27", "call_of_duty", "auto"], default="auto")
    parser.add_argument("--outcome-confidence", type=float, default=0.7)
    parser.add_argument("--outcome-interval", type=float, default=0.5)

    # Visual
    parser.add_argument("--visual", action="store_true", help="Enable visual lobe")
    parser.add_argument("--visual-api-key", help="VLM API key")
    parser.add_argument("--visual-sample-rate", type=int, default=30)

    # Trio-retina (w3bstream validation)
    parser.add_argument("--trio", action="store_true", help="Enable trio-retina w3bstream validation")
    parser.add_argument("--trio-wasm-path", default="w3bstream_applet.wasm", help="Path to w3bstream applet WASM")
    parser.add_argument("--trio-validate-on-ingest", action="store_true", help="Validate each event at ingestion")
    parser.add_argument("--trio-validate-on-flush", action="store_true", help="Validate batched events periodically")
    parser.add_argument("--trio-flush-interval", type=float, default=30.0, help="Batch flush interval (seconds)")
    parser.add_argument("--trio-block-rpc", default="https://babel-api.testnet.iotex.io", help="IoTeX RPC for block number")
    parser.add_argument("--trio-node-session-verify", action="store_true", help="Enable node/session verify")
    parser.add_argument("--trio-events-root-verify", action="store_true", help="Verify events merkle root")
    parser.add_argument("--trio-pq-commitment-source", default="mock", choices=["mock", "real"], help="PQ commitment source")
    parser.add_argument("--trio-use-python-wasmtime", action="store_true", default=True, help="Use wasmtime Python bindings instead of CLI")

    # Output
    parser.add_argument("--jsonl-path", help="JSONL output path")
    parser.add_argument("--enable-ws", action="store_true", default=True, help="Enable WebSocket")
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=8765)

    # Test config
    parser.add_argument("--duration", type=float, default=30.0, help="Test duration (seconds)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    parser.add_argument("--dry-run", action="store_true", help="Initialize but don't run")

    args = parser.parse_args()

    setup_logging(args.log_level)

    # Hardware detection only
    if args.detect_only:
        print_hardware_info()
        return 0

    # Create config
    config = create_test_config(args)

    # Create optional trio-retina config
    trio_config = None
    if TRIO_AVAILABLE and args.trio:
        trio_config = TrioRetinaConfig(
            enabled=True,
            wasm_path=args.trio_wasm_path,
            validate_on_ingest=args.trio_validate_on_ingest,
            validate_on_flush=args.trio_validate_on_flush or not args.trio_validate_on_ingest,
            flush_interval_s=args.trio_flush_interval,
            block_rpc_url=args.trio_block_rpc,
            node_session_verify=args.trio_node_session_verify,
            retina_events_root_verify=args.trio_events_root_verify,
            pq_commitment_source=args.trio_pq_commitment_source,
            use_python_wasmtime=args.trio_use_python_wasmtime,
        )
        log.info("Trio-retina validation enabled")

    # Validate
    errors = config.validate()
    if errors:
        for e in errors:
            log.error("Config error: %s", e)
        return 1

    # Print hardware info
    print_hardware_info()

    # Print config summary
    print("\n" + "="*60)
    print("INTEGRATION TEST CONFIG")
    print("="*60)
    print(f"Session ID:     {config.session_id}")
    print(f"Session Head:   {config.session_head_ns}")
    print(f"Device ID:      {config.device_id_hex or '(auto)'}")
    print(f"JSONL Output:   {config.jsonl_path or '(none)'}")
    print(f"WebSocket:      {'enabled' if config.enable_ws else 'disabled'} ({config.ws_host}:{config.ws_port})")
    print(f"Trio-retina:    {'enabled' if trio_config and trio_config.enabled else 'disabled'}")
    print(f"Duration:       {args.duration}s")
    print("\nLobes:")
    print(f"  Streamer:     {'ON' if config.streamer.enabled else 'OFF'} (device={config.streamer.device_index}, fps={config.streamer.fps_target})")
    print(f"  Controller:   {'ON' if config.controller.enabled else 'OFF'} (VID={config.controller.device_vid}, PID={config.controller.device_pid})")
    print(f"  Screen:       {'ON' if config.screen.enabled else 'OFF'} (monitor={config.screen.monitor_index}, method={config.screen.capture_method})")
    print(f"  Outcome:      {'ON' if config.outcome.enabled else 'OFF'} (profile={config.outcome.game_profile.value})")
    print(f"  Visual:       {'ON' if config.visual.enabled else 'OFF'} (sample_rate={config.visual.frame_sample_rate})")
    print("="*60 + "\n")

    if args.dry_run:
        print("Dry run complete - config valid")
        return 0

    # Run integration test
    app = IntegrationTestApp(config, duration_s=args.duration, trio_config=trio_config)

    if not app.initialize():
        log.error("Failed to initialize")
        return 1

    result = app.run()

    # Print results
    print("\n" + "="*60)
    print("INTEGRATION TEST RESULTS")
    print("="*60)
    print(f"Success:        {result['success']}")
    print(f"Session ID:     {result['session_id']}")
    print(f"Duration:       {result['duration_s']}s")
    print(f"Events Received: {result['stats']['events_received']}")
    print(f"Presence Reports: {result['stats']['presence_reports']}")
    print(f"Anomalies:      {result['stats']['anomalies_detected']}")
    print("\nLobe Events:")
    for lobe, count in result['stats']['lobe_events'].items():
        print(f"  {lobe}: {count}")
    print("\nLobe Status:")
    for lobe, status in result['lobe_status'].items():
        print(f"  {lobe}: {status}")
    print("="*60)

    return 0 if result['success'] else 1


if __name__ == "__main__":
    sys.exit(main())