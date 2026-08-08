"""Tests for the tool-call parse-execute loop (Trio P3 mid-generation)."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import pytest

from qoresence.a2a.tool_loop import (
    ToolCallResult,
    ToolLoopOutput,
    execute_tool_calls,
    format_tool_results_for_prompt,
    parse_tool_calls,
    run_tool_loop,
    strip_tool_calls,
)
from qoresence.a2a.tools import ToolDef, ToolRegistry, create_default_registry

# Build marker strings via chr() to avoid literal tags in source
_TC_OPEN = chr(60) + "tool_call" + chr(62)      # <tool_call>
_TC_CLOSE = chr(60) + "/tool_call" + chr(62)     # </tool_call>


def _tc(name, **args):
    """Build a tool_call tag string."""
    return _TC_OPEN + json.dumps({"name": name, "arguments": args}) + _TC_CLOSE


# ── Parsing ──────────────────────────────────────────────────────────────────


def test_parse_tool_call_tag():
    """Should parse tool_call blocks."""
    response = f"Some text {_tc('query-memory', event_type='outcome_event')} more text"
    calls = parse_tool_calls(response)
    assert len(calls) == 1
    assert calls[0]["name"] == "query-memory"
    assert calls[0]["arguments"]["event_type"] == "outcome_event"


def test_parse_multiple_tool_calls():
    """Should parse multiple tool_call blocks."""
    t1 = _tc("query-memory", event_type="outcome_event")
    t2 = _tc("zoom-redetect", region="scoreboard")
    response = f"{t1} and {t2}"
    calls = parse_tool_calls(response)
    assert len(calls) == 2
    assert calls[0]["name"] == "query-memory"
    assert calls[1]["name"] == "zoom-redetect"


def test_parse_no_tool_calls():
    """Should return empty list when no tool calls present."""
    calls = parse_tool_calls("Just a regular response with no tools")
    assert calls == []


def test_parse_invalid_json_in_tag():
    """Should skip invalid JSON in tool_call blocks."""
    tag = _TC_OPEN + "not valid json" + _TC_CLOSE
    calls = parse_tool_calls(tag)
    assert calls == []


def test_parse_uses_params_alias():
    """Should accept 'params' as alias for 'arguments'."""
    inner = json.dumps({"name": "query-memory", "params": {"limit": 5}})
    calls = parse_tool_calls(_TC_OPEN + inner + _TC_CLOSE)
    assert len(calls) == 1
    assert calls[0]["arguments"]["limit"] == 5


# ── Stripping ────────────────────────────────────────────────────────────────


def test_strip_tool_calls():
    """Should remove tool_call blocks from response."""
    tag = _tc("query-memory", event_type="outcome_event")
    response = f"Before {tag} After"
    cleaned = strip_tool_calls(response)
    assert "query-memory" not in cleaned
    assert "Before" in cleaned
    assert "After" in cleaned


def test_strip_no_tool_calls():
    """Should return unchanged when no tool calls present."""
    text = "Just a regular response"
    assert strip_tool_calls(text) == text


# ── Execution ────────────────────────────────────────────────────────────────


def test_execute_tool_calls():
    """Should execute tool calls via registry."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        now = time.time()
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "outcome_event", "clock_ns": 1,
                "ts_ns": int(now * 1e9),
                "source_lobe": "outcome",
                "payload": {"event_name": "touchdown"},
            }) + "\n")

        reg = create_default_registry(jsonl_path=jsonl_path)
        calls = [{"name": "query-memory", "arguments": {"event_type": "outcome_event"}}]
        results = execute_tool_calls(calls, reg)

        assert len(results) == 1
        assert results[0].name == "query-memory"
        assert results[0].result["count"] == 1
        assert results[0].error is None


def test_execute_tool_calls_unknown_tool():
    """Should return error for unknown tools."""
    reg = ToolRegistry()
    calls = [{"name": "nonexistent", "arguments": {}}]
    results = execute_tool_calls(calls, reg)
    assert results[0].error == "tool_not_found"


def test_execute_tool_calls_depth_bound():
    """Should stop when depth bound is exceeded."""
    reg = ToolRegistry(max_depth=1)
    reg.register(ToolDef(
        name="echo", description="echo", parameters={},
        handler=lambda **kw: {"ok": True},
    ))
    calls = [
        {"name": "echo", "arguments": {}},
        {"name": "echo", "arguments": {}},
    ]
    results = execute_tool_calls(calls, reg)
    assert len(results) == 2
    assert results[0].error is None
    assert results[1].error == "depth_bound_exceeded"


# ── Formatting ───────────────────────────────────────────────────────────────


def test_format_tool_results():
    """Should format tool results for prompt injection."""
    results = [ToolCallResult(
        name="query-memory",
        arguments={"event_type": "outcome_event"},
        result={"events": [{"type": "outcome_event"}], "count": 1},
    )]
    text = format_tool_results_for_prompt(results)
    assert "query-memory" in text
    assert "Tool call results:" in text


def test_format_tool_results_empty():
    """Should return empty string for no results."""
    assert format_tool_results_for_prompt([]) == ""


def test_format_tool_results_with_error():
    """Should format error results."""
    results = [ToolCallResult(
        name="nonexistent",
        arguments={},
        result={"error": "tool_not_found"},
        error="tool_not_found",
    )]
    text = format_tool_results_for_prompt(results)
    assert "ERROR" in text
    assert "tool_not_found" in text


# ── Full loop ────────────────────────────────────────────────────────────────


def test_run_tool_loop_no_tool_calls():
    """Loop should exit immediately if no tool calls in response."""
    reg = ToolRegistry()
    output = run_tool_loop("Just a regular response", reg)
    assert output.final_response == "Just a regular response"
    assert output.tool_calls == []
    assert output.rounds == 1
    assert output.used_tools is False


def test_run_tool_loop_with_tool_call_no_callback():
    """Loop should execute tools and strip markers without callback."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        now = time.time()
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "type": "outcome_event", "clock_ns": 1,
                "ts_ns": int(now * 1e9),
                "source_lobe": "outcome",
                "payload": {"event_name": "touchdown"},
            }) + "\n")

        reg = create_default_registry(jsonl_path=jsonl_path)
        tag = _tc("query-memory", event_type="outcome_event")
        response = f"Let me check {tag} the game is exciting"

        output = run_tool_loop(response, reg)
        assert output.used_tools is True
        assert len(output.tool_calls) == 1
        assert output.tool_calls[0].name == "query-memory"
        # Tool call markers should be stripped
        assert "query-memory" not in output.final_response
        assert "exciting" in output.final_response


def test_run_tool_loop_with_callback():
    """Loop should use callback for follow-up LLM calls."""
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="echo", description="echo", parameters={},
        handler=lambda **kw: {"ok": True},
    ))

    call_count = [0]

    def callback(tool_text: str) -> str:
        call_count[0] += 1
        return f"Final response after tools (round {call_count[0]})"

    tag = _tc("echo")
    response = f"I need to call a tool {tag}"

    output = run_tool_loop(response, reg, max_rounds=3, llm_callback=callback)
    assert output.used_tools is True
    assert "Final response" in output.final_response
    assert call_count[0] == 1  # One follow-up call


def test_run_tool_loop_max_rounds():
    """Loop should respect max_rounds."""
    reg = ToolRegistry()
    reg.register(ToolDef(
        name="echo", description="echo", parameters={},
        handler=lambda **kw: {"ok": True},
    ))

    tag = _tc("echo")

    def callback(tool_text: str) -> str:
        return f"More {tag}"

    response = f"Start {tag}"
    output = run_tool_loop(response, reg, max_rounds=2, llm_callback=callback)
    assert output.rounds <= 2


def test_tool_loop_output_summary():
    """tool_summary should produce human-readable summary."""
    output = ToolLoopOutput(
        final_response="test",
        tool_calls=[
            ToolCallResult(name="query-memory", arguments={}, result={"count": 3}),
            ToolCallResult(name="zoom-redetect", arguments={}, result={"detections": []}),
        ],
    )
    summary = output.tool_summary()
    assert "query-memory:3" in summary
    assert "zoom-redetect:0" in summary


def test_tool_loop_output_summary_empty():
    """tool_summary should return empty string for no tool calls."""
    output = ToolLoopOutput(final_response="test")
    assert output.tool_summary() == ""


def test_tool_loop_output_summary_with_error():
    """tool_summary should include errors."""
    output = ToolLoopOutput(
        final_response="test",
        tool_calls=[
            ToolCallResult(name="bad", arguments={}, result={"error": "failed"}, error="failed"),
        ],
    )
    summary = output.tool_summary()
    assert "bad:error" in summary
