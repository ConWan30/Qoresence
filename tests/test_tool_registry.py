"""Tests for Phase 7.3: Typed tool registry for A2A (Trio Principle 3)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
from qoresence.a2a.tools import (
    ToolDef,
    ToolRegistry,
    create_default_registry,
    make_query_memory_tool,
    make_zoom_redetect_tool,
)
from tests.conftest import put_live_coupling_ticket

# ── ToolRegistry basics ──────────────────────────────────────────────────────


def test_registry_register_and_get():
    """A registered tool should be retrievable by name."""
    reg = ToolRegistry()

    def handler(**params):
        return {"result": "ok"}

    tool = ToolDef(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        handler=handler,
    )
    reg.register(tool)

    assert reg.get("test_tool") is not None
    assert reg.get("nonexistent") is None


def test_registry_list_tools():
    """list_tools should return tool definitions without handlers."""
    reg = ToolRegistry()
    reg.register(
        ToolDef(
            name="tool_a",
            description="Tool A",
            parameters={"type": "object"},
            handler=lambda **kw: {"a": 1},
        )
    )
    reg.register(
        ToolDef(
            name="tool_b",
            description="Tool B",
            parameters={"type": "object"},
            handler=lambda **kw: {"b": 2},
        )
    )

    tools = reg.list_tools()
    assert len(tools) == 2
    names = [t["name"] for t in tools]
    assert "tool_a" in names
    assert "tool_b" in names
    # Should not include handler
    assert "handler" not in tools[0]


def test_registry_call_executes_handler():
    """Calling a tool should execute its handler and return the result."""
    reg = ToolRegistry()

    def handler(x: int = 0, y: int = 0):
        return {"sum": x + y}

    reg.register(
        ToolDef(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
            },
            handler=handler,
        )
    )

    result = reg.call("add", x=3, y=4)
    assert result == {"sum": 7}
    assert reg.call_count == 1


def test_registry_call_unknown_tool():
    """Calling an unregistered tool should return an error dict."""
    reg = ToolRegistry()
    result = reg.call("nonexistent")
    assert result["error"] == "tool_not_found"
    assert result["name"] == "nonexistent"


def test_registry_depth_bound():
    """Tool calls should be limited by MAX_TOOL_DEPTH."""
    reg = ToolRegistry(max_depth=2)
    reg.register(
        ToolDef(
            name="echo",
            description="Echo",
            parameters={"type": "object"},
            handler=lambda **kw: {"ok": True},
        )
    )

    assert reg.call("echo") == {"ok": True}
    assert reg.call("echo") == {"ok": True}
    # Third call should hit depth bound
    result = reg.call("echo")
    assert result["error"] == "depth_bound_exceeded"
    assert result["max_depth"] == 2


def test_registry_reset_depth():
    """reset_depth should allow new calls after a cycle."""
    reg = ToolRegistry(max_depth=1)
    reg.register(
        ToolDef(
            name="echo",
            description="Echo",
            parameters={"type": "object"},
            handler=lambda **kw: {"ok": True},
        )
    )

    reg.call("echo")
    assert reg.call("echo")["error"] == "depth_bound_exceeded"

    reg.reset_depth()
    assert reg.call("echo") == {"ok": True}


def test_registry_handler_exception_returns_error():
    """A handler that raises should return an error dict, not crash."""
    reg = ToolRegistry()

    def bad_handler(**kw):
        raise ValueError("boom")

    reg.register(
        ToolDef(
            name="bad",
            description="Bad tool",
            parameters={"type": "object"},
            handler=bad_handler,
        )
    )

    result = reg.call("bad")
    assert result["error"] == "tool_execution_failed"
    assert "boom" in result["detail"]


# ── query-memory tool ────────────────────────────────────────────────────────


def test_query_memory_searches_jsonl():
    """query-memory should find events in the JSONL log."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        # Write some test events
        now = time.time()
        events = [
            {
                "type": "outcome_event",
                "clock_ns": 1,
                "ts_ns": int(now * 1e9),
                "source_lobe": "outcome",
                "payload": {"event_name": "touchdown", "side": "home"},
            },
            {
                "type": "outcome_event",
                "clock_ns": 2,
                "ts_ns": int(now * 1e9),
                "source_lobe": "outcome",
                "payload": {"event_name": "field_goal", "side": "away"},
            },
            {
                "type": "visual_context",
                "clock_ns": 3,
                "ts_ns": int(now * 1e9),
                "source_lobe": "visual",
                "payload": {"game_state": "gameplay"},
            },
        ]
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        tool = make_query_memory_tool(jsonl_path)
        result = tool.handler(event_type="outcome_event")

        assert result["count"] == 2
        assert all(e["type"] == "outcome_event" for e in result["events"])


def test_query_memory_filter_by_event_name():
    """query-memory should filter by event_name in payload."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        now = time.time()
        events = [
            {
                "type": "outcome_event",
                "clock_ns": 1,
                "ts_ns": int(now * 1e9),
                "source_lobe": "outcome",
                "payload": {"event_name": "touchdown"},
            },
            {
                "type": "outcome_event",
                "clock_ns": 2,
                "ts_ns": int(now * 1e9),
                "source_lobe": "outcome",
                "payload": {"event_name": "field_goal"},
            },
        ]
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        tool = make_query_memory_tool(jsonl_path)
        result = tool.handler(event_type="outcome_event", event_name="touchdown")

        assert result["count"] == 1
        assert result["events"][0]["payload"]["event_name"] == "touchdown"


def test_query_memory_time_filter():
    """query-memory should filter by seconds_back."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        now = time.time()
        # Old event (10 minutes ago)
        old_ts = int((now - 600) * 1e9)
        # Recent event (1 second ago)
        new_ts = int((now - 1) * 1e9)
        events = [
            {
                "type": "outcome_event",
                "clock_ns": 1,
                "ts_ns": old_ts,
                "source_lobe": "outcome",
                "payload": {"event_name": "old"},
            },
            {
                "type": "outcome_event",
                "clock_ns": 2,
                "ts_ns": new_ts,
                "source_lobe": "outcome",
                "payload": {"event_name": "recent"},
            },
        ]
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        tool = make_query_memory_tool(jsonl_path)
        result = tool.handler(event_type="outcome_event", seconds_back=60)

        assert result["count"] == 1
        assert result["events"][0]["payload"]["event_name"] == "recent"


def test_query_memory_nonexistent_log():
    """query-memory should return empty result if log doesn't exist."""
    tool = make_query_memory_tool("/nonexistent/path/events.jsonl")
    result = tool.handler()
    assert result["count"] == 0
    assert result["error"] == "log_not_found"


def test_query_memory_limit():
    """query-memory should respect the limit parameter."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        now = time.time()
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for i in range(50):
                f.write(
                    json.dumps(
                        {
                            "type": "outcome_event",
                            "clock_ns": i,
                            "ts_ns": int(now * 1e9),
                            "source_lobe": "outcome",
                            "payload": {"event_name": f"event_{i}"},
                        }
                    )
                    + "\n"
                )

        tool = make_query_memory_tool(jsonl_path)
        result = tool.handler(event_type="outcome_event", limit=5)
        assert result["count"] == 5


# ── zoom-redetect tool ───────────────────────────────────────────────────────


def test_zoom_redetect_with_callback():
    """zoom-redetect should call the provided callback."""

    def callback(region: str, vocabulary: list[str]) -> dict:
        return {"detections": [{"class": "scoreboard", "confidence": 0.95}]}

    tool = make_zoom_redetect_tool(callback)
    result = tool.handler(region="top-left", vocabulary=["scoreboard", "timer"])

    assert "detections" in result
    assert len(result["detections"]) == 1
    assert result["detections"][0]["class"] == "scoreboard"
    assert result["region"] == "top-left"


def test_zoom_redetect_no_callback():
    """zoom-redetect without a callback should return a no-op error."""
    tool = make_zoom_redetect_tool(None)
    result = tool.handler(region="scoreboard")

    assert result["error"] == "no_callback_wired"
    assert result["detections"] == []


def test_zoom_redetect_callback_exception():
    """zoom-redetect should handle callback exceptions gracefully."""

    def bad_callback(region: str, vocabulary: list[str]) -> dict:
        raise RuntimeError("visual lobe offline")

    tool = make_zoom_redetect_tool(bad_callback)
    result = tool.handler(region="full")
    assert result["error"] == "callback_failed"
    assert "visual lobe offline" in result["detail"]


# ── Default registry factory ─────────────────────────────────────────────────


def test_create_default_registry():
    """create_default_registry should register query-memory and zoom-redetect."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        reg = create_default_registry(jsonl_path=jsonl_path)

        assert reg.get("query-memory") is not None
        assert reg.get("zoom-redetect") is not None


def test_create_default_registry_no_jsonl():
    """create_default_registry without jsonl_path should only have zoom-redetect."""
    reg = create_default_registry()
    assert reg.get("query-memory") is None
    assert reg.get("zoom-redetect") is not None


# ── Orchestrator integration ─────────────────────────────────────────────────


def test_orchestrator_has_tool_registry():
    """The orchestrator should have a tool registry."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
    assert orch.tools is not None
    assert "zoom-redetect" in [t["name"] for t in orch.tools.list_tools()]
    reset_a2a_orchestrator()


def test_orchestrator_stats_include_tools():
    """Orchestrator stats should include available tools."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
    stats = orch.stats()
    assert "tools" in stats
    assert len(stats["tools"]) >= 1
    reset_a2a_orchestrator()


def test_orchestrator_tool_depth_reset_per_cycle():
    """Tool depth should reset at the start of each run_cycle."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
    # Make some tool calls
    orch.tools.call("zoom-redetect", region="full")
    assert orch.tools.call_count > 0

    # Run a cycle — should reset depth
    put_live_coupling_ticket()
    orch.run_cycle(situation={"game_category": "football"}, reason="force")
    assert orch.tools.call_count == 0  # reset at start of cycle

    reset_a2a_orchestrator()


def test_orchestrator_query_memory_with_jsonl():
    """Orchestrator with jsonl_path should have a working query-memory tool."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        # Write a test event
        now = time.time()
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "type": "outcome_event",
                        "clock_ns": 1,
                        "ts_ns": int(now * 1e9),
                        "source_lobe": "outcome",
                        "payload": {"event_name": "touchdown"},
                    }
                )
                + "\n"
            )

        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0, jsonl_path=str(jsonl_path))
        result = orch.tools.call("query-memory", event_type="outcome_event")

        assert result["count"] == 1
        assert result["events"][0]["payload"]["event_name"] == "touchdown"

        reset_a2a_orchestrator()
