"""
Phase 2 Tests — Session Authority + Event Bus

Synthetic multi-lobe test proving shared identity and clock.
"""

from __future__ import annotations

import json
import tempfile
from enum import StrEnum
from pathlib import Path

import pytest

from qoresence.core import (
    BaseEvent,
    EventType,
    RetinaEventBus,
    SessionAuthority,
    SourceLobe,
    clock_ns,
    make_event,
)


class TestSessionAuthority:
    """Tests for SessionAuthority.mint()"""

    def test_mint_generates_all_fields(self):
        identity = SessionAuthority.mint()
        assert identity.session_id.startswith("qoresence_")
        assert identity.session_head_ns > 0
        assert identity.device_id_hex == ""  # default empty

    def test_mint_with_custom_session_id(self):
        identity = SessionAuthority.mint(session_id="my_custom_session")
        assert identity.session_id == "my_custom_session"

    def test_mint_with_device_id(self):
        device_id = "a" * 64
        identity = SessionAuthority.mint(device_id_hex=device_id)
        assert identity.device_id_hex == device_id

    def test_mint_with_custom_head_ns(self):
        custom_ns = 1234567890123456789
        identity = SessionAuthority.mint(session_head_ns=custom_ns)
        assert identity.session_head_ns == custom_ns

    def test_current_session_tracking(self):
        SessionAuthority.clear()
        identity = SessionAuthority.mint(session_id="track_test")
        assert SessionAuthority.current() == identity

    def test_clear_session(self):
        SessionAuthority.mint(session_id="to_clear")
        SessionAuthority.clear()
        assert SessionAuthority.current() is None

    def test_from_env(self):
        import os

        os.environ["QORESENCE_SESSION_ID"] = "env_session"
        os.environ["QORESENCE_DEVICE_ID_HEX"] = "b" * 64
        os.environ["QORESENCE_SESSION_HEAD_NS"] = "9999999999"
        try:
            identity = SessionAuthority.from_env()
            assert identity.session_id == "env_session"
            assert identity.device_id_hex == "b" * 64
            assert identity.session_head_ns == 9999999999
        finally:
            del os.environ["QORESENCE_SESSION_ID"]
            del os.environ["QORESENCE_DEVICE_ID_HEX"]
            del os.environ["QORESENCE_SESSION_HEAD_NS"]


class TestBaseEvent:
    """Tests for BaseEvent validation and serialization."""

    def test_valid_event_creation(self):
        event = make_event(
            session_id="test_session",
            clock_ns=clock_ns(),
            source_lobe=SourceLobe.STREAMER,
            event_type=EventType.ACTIVITY,
            payload={"level": "high", "motion": 0.5},
        )
        assert event.session_id == "test_session"
        assert event.source_lobe == SourceLobe.STREAMER
        assert event.type == EventType.ACTIVITY

    def test_event_serialization_roundtrip(self):
        original = make_event(
            session_id="test_session",
            clock_ns=1234567890,
            source_lobe=SourceLobe.CONTROLLER,
            event_type=EventType.TRIGGER_ONSET,
            payload={"trigger": "R2", "amplitude": 0.8},
            session_head_ns=1234567000,
        )
        data = original.to_dict()
        restored = BaseEvent.from_dict(data)
        assert restored.session_id == original.session_id
        assert restored.clock_ns == original.clock_ns
        assert restored.source_lobe == original.source_lobe
        assert restored.type == original.type
        assert restored.payload == original.payload
        assert restored.session_head_ns == original.session_head_ns

    def test_event_rejects_missing_session_id(self):
        with pytest.raises(ValueError):
            make_event(
                session_id="",
                clock_ns=clock_ns(),
                source_lobe=SourceLobe.STREAMER,
                event_type=EventType.ACTIVITY,
                payload={},
            )

    def test_event_rejects_invalid_clock_ns(self):
        with pytest.raises(ValueError):
            make_event(
                session_id="test",
                clock_ns=0,
                source_lobe=SourceLobe.STREAMER,
                event_type=EventType.ACTIVITY,
                payload={},
            )


class TestRetinaEventBus:
    """Tests for RetinaEventBus."""

    def test_bus_accepts_valid_events(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)

            event = make_event(
                session_id="test_session",
                clock_ns=clock_ns(),
                source_lobe=SourceLobe.STREAMER,
                event_type=EventType.ACTIVITY,
                payload={"level": "high"},
            )
            assert bus.emit(event) is True
            assert bus.events_emitted == 1
            bus.close()

    def test_bus_rejects_wrong_session_id(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="session_A", jsonl_path=jsonl_path, enable_ws=False)

            event = make_event(
                session_id="session_B",  # Different session!
                clock_ns=clock_ns(),
                source_lobe=SourceLobe.STREAMER,
                event_type=EventType.ACTIVITY,
                payload={"level": "high"},
            )
            assert bus.emit(event) is False
            assert bus.events_rejected == 1
            assert bus.events_emitted == 0
            bus.close()

    def test_bus_rejects_missing_required_fields(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="test_session", jsonl_path=jsonl_path, enable_ws=False)

            # Event with no clock_ns (will be auto-filled but session_id validation happens first)
            event = BaseEvent(
                session_id="test_session",
                clock_ns=0,  # Invalid - will be caught
                source_lobe=SourceLobe.STREAMER,
                type=EventType.ACTIVITY,
                payload={},
            )
            assert bus.emit(event) is False
            assert bus.events_rejected == 1
            bus.close()

    def test_bus_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="jsonl_test", jsonl_path=jsonl_path, enable_ws=False)

            event = make_event(
                session_id="jsonl_test",
                clock_ns=clock_ns(),
                source_lobe=SourceLobe.STREAMER,
                event_type=EventType.ACTIVITY,
                payload={"level": "high", "motion": 0.5},
            )
            bus.emit(event)

            # Read back and verify
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1
            data = json.loads(lines[0])
            assert data["session_id"] == "jsonl_test"
            assert data["source_lobe"] == "streamer"
            assert data["type"] == "activity"
            assert data["payload"]["level"] == "high"
            bus.close()

    def test_bus_in_process_subscription(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="sub_test", jsonl_path=jsonl_path, enable_ws=False)

            received = []

            def callback(event):
                received.append(event)

            unsubscribe = bus.subscribe(callback)

            event = make_event(
                session_id="sub_test",
                clock_ns=clock_ns(),
                source_lobe=SourceLobe.STREAMER,
                event_type=EventType.FRAME_STATS,
                payload={"n": 1, "fps": 30.0},
            )
            bus.emit(event)

            assert len(received) == 1
            assert received[0].type == EventType.FRAME_STATS

            # Unsubscribe and verify no more callbacks
            unsubscribe()
            bus.emit(event)
            assert len(received) == 1  # Still 1
            bus.close()

    def test_emit_raw_convenience(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="raw_test", jsonl_path=jsonl_path, enable_ws=False)

            assert (
                bus.emit_raw(
                    source_lobe=SourceLobe.CONTROLLER,
                    event_type="trigger_onset",
                    payload={"trigger": "R2", "amplitude": 0.9},
                )
                is True
            )
            assert bus.events_emitted == 1

            class _TwinLobe(StrEnum):
                STREAMER = "streamer"

            assert (
                bus.emit_raw(
                    source_lobe=_TwinLobe.STREAMER,
                    event_type="session_start",
                    payload={"advisory": True},
                )
                is True
            )
            assert jsonl_path.exists()
            bus.close()


class TestMultiLobeSharedIdentity:
    """
    SYNTHETIC MULTI-LOBE TEST — Phase 2 acceptance criteria.

    Proves that multiple fake lobes emitting to the same bus
    share identical session_id and clock_ns.
    """

    def test_synthetic_multi_lobe_shared_identity(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "multi_lobe.jsonl"
            bus = RetinaEventBus(
                session_id="multi_lobe_session", jsonl_path=jsonl_path, enable_ws=False
            )

            # Simulate 3 lobes emitting events
            lobes = [
                SourceLobe.STREAMER,
                SourceLobe.CONTROLLER,
                SourceLobe.SCREEN,
            ]

            # All lobes use the SAME session_id and clock source
            session_id = "multi_lobe_session"
            head_ns = clock_ns()

            events_emitted = 0
            for lobe in lobes:
                for i in range(3):  # 3 events per lobe
                    event = make_event(
                        session_id=session_id,
                        clock_ns=clock_ns(),  # Each gets current monotonic time
                        source_lobe=lobe,
                        event_type=EventType.ACTIVITY
                        if lobe == SourceLobe.STREAMER
                        else EventType.CONTROLLER_EVENT,
                        payload={"seq": i, "lobe": lobe.value},
                        session_head_ns=head_ns,
                    )
                    assert bus.emit(event) is True
                    events_emitted += 1

            assert bus.events_emitted == 9  # 3 lobes * 3 events

            # Read JSONL and verify ALL events have same session_id
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 9

            for line in lines:
                data = json.loads(line)
                assert data["session_id"] == "multi_lobe_session", f"Session ID mismatch: {data}"
                assert "clock_ns" in data
                assert data["clock_ns"] > 0
                assert data["source_lobe"] in ["streamer", "controller", "screen"]
                assert "session_head_ns" in data
                assert data["session_head_ns"] == head_ns
            bus.close()

    def test_clock_ns_monotonic_across_lobes(self):
        """Verify clock_ns is monotonic and shared across lobes."""
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "clock_test.jsonl"
            bus = RetinaEventBus(session_id="clock_test", jsonl_path=jsonl_path, enable_ws=False)

            # Simulate rapid multi-lobe emissions
            clocks = []
            for _ in range(10):
                for lobe in [SourceLobe.STREAMER, SourceLobe.CONTROLLER]:
                    event = make_event(
                        session_id="clock_test",
                        clock_ns=clock_ns(),
                        source_lobe=lobe,
                        event_type=EventType.HEARTBEAT,
                        payload={},
                    )
                    bus.emit(event)
                    clocks.append(event.clock_ns)

            # All clock_ns should be strictly increasing (monotonic)
            for i in range(1, len(clocks)):
                assert clocks[i] >= clocks[i - 1], "clock_ns not monotonic"
            bus.close()

    def test_eventbus_stats(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "stats.jsonl"
            bus = RetinaEventBus(session_id="stats_test", jsonl_path=jsonl_path, enable_ws=False)

            # Emit 5 valid
            for i in range(5):
                bus.emit_raw(SourceLobe.STREAMER, "activity", {"n": i})

            # Emit 1 invalid (wrong session) - use BaseEvent directly
            from qoresence.core.types import BaseEvent

            wrong_session_event = BaseEvent(
                session_id="wrong_session",
                clock_ns=clock_ns(),
                source_lobe=SourceLobe.STREAMER,
                type=EventType.ACTIVITY,
                payload={"n": 999},
            )
            bus.emit(wrong_session_event)

            stats = bus.stats()
            assert stats["session_id"] == "stats_test"
            assert stats["events_emitted"] == 5
            assert stats["events_rejected"] == 1
            bus.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
