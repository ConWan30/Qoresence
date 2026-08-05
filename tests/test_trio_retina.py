"""
Phase 11 Tests — trio-retina Integration

Tests for Qoresence × trio-retina w3bstream validation integration.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from qoresence.core import RetinaUnifiedConfig, SessionAuthority, RetinaEventBus, SourceLobe
from qoresence.trio import (
    TrioRetinaConfig,
    EvmLogPayload,
    build_evm_log_payload,
    compute_node_id,
    compute_payload_hash,
    compute_events_root,
    mock_pq_commitment,
    mock_signature,
    try_real_pq_commitment,
    WasmtimeRunner,
    WasmResult,
    TrioRetinaValidator,
    ValidationResult,
    create_validator,
)


class TestTrioRetinaConfig:
    """Tests for TrioRetinaConfig."""

    def test_default_config_disabled(self):
        """Default config should be disabled."""
        config = TrioRetinaConfig()
        assert config.enabled is False
        assert config.wasm_path == "w3bstream_applet.wasm"

    def test_enabled_config(self):
        """Enabled config should have all fields set."""
        config = TrioRetinaConfig(
            enabled=True,
            wasm_path="/custom/path.wasm",
            validate_on_ingest=True,
            flush_interval_s=60.0,
        )
        assert config.enabled is True
        assert config.wasm_path == "/custom/path.wasm"
        assert config.validate_on_ingest is True
        assert config.flush_interval_s == 60.0

    def test_resolve_wasm_path(self):
        """WASM path resolution."""
        config = TrioRetinaConfig(wasm_path="test.wasm")
        # Should return path even if not exists (validated at runtime)
        path = config.resolve_wasm_path(Path("/tmp"))
        assert path.name == "test.wasm"


class TestEvmLogPayload:
    """Tests for EvmLogPayload serialization."""

    def test_payload_creation(self):
        """Create payload with required fields."""
        payload = EvmLogPayload(
            device_id="a" * 64,
            block_number=12345,
            payload_hash="b" * 64,
            signature="c" * 64,
            pq_commitment="d" * 64,
        )
        assert payload.device_id == "a" * 64
        assert payload.block_number == 12345

    def test_payload_json_serialization(self):
        """Payload should serialize to JSON."""
        payload = EvmLogPayload(
            device_id="a" * 64,
            block_number=12345,
            payload_hash="b" * 64,
            signature="c" * 64,
            pq_commitment="d" * 64,
            retina_state_commitment="e" * 64,
            node_id="f" * 64,
        )
        json_str = payload.to_json()
        data = json.loads(json_str)
        assert data["device_id"] == "a" * 64
        assert data["block_number"] == 12345
        assert data["retina_state_commitment"] == "e" * 64
        assert data["node_id"] == "f" * 64

    def test_payload_json_deserialization(self):
        """Payload should deserialize from JSON."""
        json_str = json.dumps({
            "device_id": "a" * 64,
            "block_number": 12345,
            "payload_hash": "b" * 64,
            "signature": "c" * 64,
            "pq_commitment": "d" * 64,
            "retina_state_commitment": "e" * 64,
            "retina_w3bstream_enforce": True,
            "events_root": "f" * 64,
            "retina_events_root_verify": False,
            "node_id": "g" * 64,
            "session_root": "h" * 64,
            "node_session_verify": True,
        })
        payload = EvmLogPayload.from_json(json_str)
        assert payload.device_id == "a" * 64
        assert payload.block_number == 12345
        assert payload.retina_w3bstream_enforce is True
        assert payload.node_session_verify is True


class TestPayloadBuilder:
    """Tests for payload building utilities."""

    def test_compute_node_id(self):
        """Node ID computation matches trio-retina standard."""
        device_id = "a" * 64
        first_session = "session_123"
        node_id = compute_node_id(device_id, first_session)
        assert len(node_id) == 64
        assert all(c in "0123456789abcdef" for c in node_id)

    def test_compute_node_id_deterministic(self):
        """Node ID should be deterministic."""
        device_id = "b" * 64
        first_session = "session_456"
        node_id1 = compute_node_id(device_id, first_session)
        node_id2 = compute_node_id(device_id, first_session)
        assert node_id1 == node_id2

    def test_compute_payload_hash(self):
        """Payload hash computation."""
        session_head = time.time_ns()
        events = [{"event_id": "evt1", "type": "test"}, {"event_id": "evt2", "type": "test"}]
        hash1 = compute_payload_hash(session_head, events)
        hash2 = compute_payload_hash(session_head, events)
        assert len(hash1) == 64
        assert hash1 == hash2

    def test_compute_events_root(self):
        """Events root computation."""
        event_ids = ["evt1", "evt2", "evt3"]
        root = compute_events_root(event_ids)
        assert len(root) == 64

    def test_compute_events_root_empty(self):
        """Empty events root should be zeros."""
        root = compute_events_root([])
        assert root == "0" * 64

    def test_mock_pq_commitment(self):
        """Mock PQ commitment should be valid 64-hex."""
        commitment = mock_pq_commitment()
        assert len(commitment) == 64
        assert commitment == "a" * 64

    def test_try_real_pq_commitment_mock_inputs(self):
        """try_real_pq_commitment should return None for mock inputs (no real proof possible)."""
        result = try_real_pq_commitment(
            biometric_snapshot_hash="a" * 64,
            claimed_player_id=1,
            feature_commitment="b" * 64,
        )
        # On Windows without npx, should return None
        # In Docker with artifacts, would return real commitment
        assert result is None or len(result) == 64

    def test_mock_signature(self):
        """Mock signature should be valid 64-hex."""
        sig = mock_signature("test_hash")
        assert len(sig) == 64

    def test_build_evm_log_payload(self):
        """Full payload builder."""
        session = SessionAuthority.mint(session_id="test_session", device_id_hex="a" * 64)
        events = [{"event_id": "evt1", "type": "test"}]
        config = TrioRetinaConfig(enabled=True)
        
        payload = build_evm_log_payload(
            session=session,
            events=events,
            config=config,
            first_session_id="first_session",
        )
        
        assert isinstance(payload, EvmLogPayload)
        assert payload.device_id == session.device_id_hex
        assert payload.node_id != ""  # Should be computed
        assert len(payload.node_id) == 64


class TestWasmtimeRunner:
    """Tests for WasmtimeRunner."""

    def test_runner_creation(self):
        """Runner should be created with config."""
        config = TrioRetinaConfig(enabled=True, wasm_path="test.wasm")
        runner = WasmtimeRunner(config)
        assert runner.config == config

    @patch('qoresence.trio.wasm.WasmtimeRunner._run_cli', new_callable=AsyncMock)
    @pytest.mark.asyncio
    async def test_run_mock(self, mock_run_cli):
        """Test run with mocked CLI."""
        mock_run_cli.return_value = WasmResult(
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=10.0,
        )
        
        config = TrioRetinaConfig(enabled=True)
        runner = WasmtimeRunner(config)
        
        payload = EvmLogPayload(
            device_id="a" * 64,
            block_number=1,
            payload_hash="b" * 64,
            signature="c" * 64,
            pq_commitment="d" * 64,
        )
        
        result = await runner.run(payload)
        assert result.exit_code == 0
        assert result.ok is True


class TestTrioRetinaValidator:
    """Tests for TrioRetinaValidator."""

    def test_validator_creation(self):
        """Validator should be created with all dependencies."""
        config = TrioRetinaConfig(enabled=True)
        session = SessionAuthority.mint(session_id="test_session")
        bus = RetinaEventBus(session_id="test_session")
        
        validator = TrioRetinaValidator(
            config=config,
            session=session,
            event_bus=bus,
        )
        
        assert validator.config == config
        assert validator.session == session
        assert validator.event_bus == bus

    def test_validator_stats_initial(self):
        """Initial stats should be zero."""
        config = TrioRetinaConfig(enabled=True)
        session = SessionAuthority.mint(session_id="test_session")
        
        validator = TrioRetinaValidator(
            config=config,
            session=session,
        )
        
        stats = validator.get_stats()
        assert stats["validations_total"] == 0
        assert stats["validations_ok"] == 0
        assert stats["validations_failed"] == 0


class TestEventBusTrioIntegration:
    """Tests for RetinaEventBus trio-retina integration."""

    def test_event_bus_with_trio_config(self):
        """Event bus should accept trio config."""
        config = TrioRetinaConfig(enabled=True)
        session = SessionAuthority.mint(session_id="test_session")
        
        bus = RetinaEventBus(
            session_id="test_session",
            trio_config=config,
            session_identity=session,
        )
        
        assert bus._trio_config == config
        assert bus._session_identity == session

    def test_init_trio_validator_requires_trio_available(self):
        """init_trio_validator should return False when trio not available."""
        bus = RetinaEventBus(session_id="test_session")
        # Without trio installed, should return False
        result = bus.init_trio_validator()
        assert result is False

    def test_get_trio_stats_disabled(self):
        """get_trio_stats should return disabled when no validator."""
        bus = RetinaEventBus(session_id="test_session")
        stats = bus.get_trio_stats()
        assert stats == {"enabled": False}


class TestCliIntegration:
    """Tests for CLI trio-retina integration."""

    def test_create_trio_config_from_args(self):
        """CLI args should create trio config."""
        import argparse
        from qoresence.trio import TrioRetinaConfig
        
        # Mock args
        args = argparse.Namespace(
            trio=True,
            trio_wasm_path="custom.wasm",
            trio_validate_on_ingest=True,
            trio_validate_on_flush=True,
            trio_flush_interval=60.0,
            trio_block_rpc="https://custom.rpc",
            trio_node_session_verify=True,
            session_id="test",
            session_head_ns=0,
            device_id="",
            jsonl_path="",
            enable_ws=True,
            ws_host="127.0.0.1",
            ws_port=8765,
            streamer=False,
            streamer_fps=30.0,
            controller=False,
            controller_rate=1000.0,
            outcome=False,
            game_profile="ncaa_football_27",
            screen=False,
            screen_fps=60.0,
            visual=False,
            visual_sample_rate=30,
            log_level="INFO",
            health_check=False,
            dry_run=False,
        )
        
        trio_config = TrioRetinaConfig(
            enabled=True,
            wasm_path=args.trio_wasm_path,
            validate_on_ingest=args.trio_validate_on_ingest,
            validate_on_flush=args.trio_validate_on_flush,
            flush_interval_s=args.trio_flush_interval,
            block_rpc_url=args.trio_block_rpc,
            node_session_verify=args.trio_node_session_verify,
        )
        assert trio_config.enabled is True
        assert trio_config.wasm_path == "custom.wasm"
        assert trio_config.validate_on_ingest is True


class TestWasmResult:
    """Tests for WasmResult."""

    def test_ok_property(self):
        """ok property should reflect exit code."""
        result_ok = WasmResult(exit_code=0, stdout="", stderr="", duration_ms=10)
        result_fail = WasmResult(exit_code=1, stdout="", stderr="", duration_ms=10)
        
        assert result_ok.ok is True
        assert result_fail.ok is False

    def test_error_descriptions(self):
        """Error descriptions for known exit codes."""
        descriptions = {
            0: "OK",
            1: "Bad pointer / null input",
            2: "UTF-8 decode error",
            3: "JSON parse error",
            4: "Block cadence invalid (not multiple of 64)",
            5: "PQ proof resolution failed",
            6: "Retina state commitment invalid",
            7: "Events root invalid",
            8: "Node/session gate failed",
        }
        for code, desc in descriptions.items():
            result = WasmResult(exit_code=code, stdout="", stderr="", duration_ms=10)
            assert result.error_description == desc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])