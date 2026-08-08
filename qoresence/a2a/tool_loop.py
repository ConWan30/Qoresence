"""Tool-call parse-execute loop for A2A agents (Trio P3 bidirectional).

Implements a multi-turn tool-call loop where the LLM can request tool
calls in its response, which are parsed, executed via the ToolRegistry,
and fed back into a follow-up LLM call. This enables agents to
re-query lower tiers mid-generation.

Protocol:
    The LLM includes tool-call requests as JSON blocks marked with
    <tool_call> tags:

        <tool_call>{"name":"query-memory","arguments":{"event_type":"outcome_event"}}</tool_call>

    The loop:
    1. Parses the LLM response for <tool_call> blocks
    2. Executes each tool via the registry (respecting depth bound)
    3. Feeds results back as a system message
    4. Re-prompts the LLM for a final response
    5. Repeats up to max_rounds (default 3)

If no tool calls are found in the response, the loop exits immediately.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from qoresence.a2a.tools import ToolRegistry

log = logging.getLogger(__name__)

# Regex to find <tool_call>...</tool_call> blocks
_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL | re.IGNORECASE,
)

# Also support markdown-fenced tool calls
_TOOL_CALL_FENCE_RE = re.compile(
    r"```tool_call\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class ToolCallResult:
    """Result of a single tool call execution."""

    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class ToolLoopOutput:
    """Output of the tool-call parse-execute loop."""

    final_response: str
    tool_calls: list[ToolCallResult] = field(default_factory=list)
    rounds: int = 0

    @property
    def used_tools(self) -> bool:
        return len(self.tool_calls) > 0

    def tool_summary(self) -> str:
        """Human-readable summary of tool calls for evidence chains."""
        if not self.tool_calls:
            return ""
        parts = []
        for tc in self.tool_calls:
            if tc.error:
                parts.append(f"{tc.name}:error({tc.error})")
            else:
                count = tc.result.get("count", len(tc.result.get("events", [])))
                parts.append(f"{tc.name}:{count}")
        return ", ".join(parts)


def parse_tool_calls(response: str) -> list[dict[str, Any]]:
    """Parse <tool_call> blocks from an LLM response.

    Returns a list of {"name": ..., "arguments": {...}} dicts.
    """
    calls: list[dict[str, Any]] = []

    # Try <tool_call> tags first
    for match in _TOOL_CALL_RE.finditer(response):
        try:
            data = json.loads(match.group(1))
            if "name" in data:
                calls.append({
                    "name": data["name"],
                    "arguments": data.get("arguments", data.get("params", {})),
                })
        except json.JSONDecodeError:
            continue

    # Try markdown-fenced tool calls
    if not calls:
        for match in _TOOL_CALL_FENCE_RE.finditer(response):
            try:
                data = json.loads(match.group(1))
                if "name" in data:
                    calls.append({
                        "name": data["name"],
                        "arguments": data.get("arguments", data.get("params", {})),
                    })
            except json.JSONDecodeError:
                continue

    return calls


def strip_tool_calls(response: str) -> str:
    """Remove <tool_call> blocks from a response, leaving clean text."""
    cleaned = _TOOL_CALL_RE.sub("", response)
    cleaned = _TOOL_CALL_FENCE_RE.sub("", cleaned)
    return cleaned.strip()


def execute_tool_calls(
    calls: list[dict[str, Any]],
    registry: ToolRegistry,
) -> list[ToolCallResult]:
    """Execute a list of tool calls via the registry.

    Respects the registry's depth bound — if exceeded, remaining
    calls return a depth_bound_exceeded error.
    """
    results: list[ToolCallResult] = []
    for call in calls:
        name = call.get("name", "")
        args = call.get("arguments", {})
        if not isinstance(args, dict):
            args = {}

        result = registry.call(name, **args)
        error = result.get("error") if isinstance(result, dict) else "invalid_result"

        results.append(ToolCallResult(
            name=name,
            arguments=args,
            result=result,
            error=error if error else None,
        ))

        # Stop if depth bound exceeded
        if error == "depth_bound_exceeded":
            break

    return results


def format_tool_results_for_prompt(results: list[ToolCallResult]) -> str:
    """Format tool results as a system message for the follow-up prompt."""
    if not results:
        return ""

    parts = ["Tool call results:"]
    for tc in results:
        if tc.error:
            parts.append(f"  {tc.name}: ERROR ({tc.error})")
        else:
            # Compact JSON for the prompt
            compact = json.dumps(tc.result, separators=(",", ":"))[:500]
            parts.append(f"  {tc.name}: {compact}")

    return "\n".join(parts)


def run_tool_loop(
    initial_response: str,
    registry: ToolRegistry,
    *,
    max_rounds: int = 3,
    llm_callback=None,
) -> ToolLoopOutput:
    """Run the tool-call parse-execute loop.

    Args:
        initial_response: The first LLM response that may contain tool calls
        registry: ToolRegistry to execute tool calls
        max_rounds: Maximum number of parse-execute-reprompt rounds
        llm_callback: Optional callback(prompt_addition) -> str for follow-up
            LLM calls. If None, the loop only executes tools from the initial
            response and returns the stripped text.

    Returns:
        ToolLoopOutput with the final response and all tool call results.
    """
    all_tool_calls: list[ToolCallResult] = []
    current_response = initial_response
    rounds = 0

    for round_num in range(max_rounds):
        rounds = round_num + 1
        calls = parse_tool_calls(current_response)
        if not calls:
            break

        # Execute tool calls
        results = execute_tool_calls(calls, registry)
        all_tool_calls.extend(results)

        # If no LLM callback, just strip and return
        if llm_callback is None:
            current_response = strip_tool_calls(current_response)
            break

        # Format results for follow-up prompt
        tool_text = format_tool_results_for_prompt(results)

        # Get follow-up response from LLM
        try:
            follow_up = llm_callback(tool_text)
            if not follow_up:
                current_response = strip_tool_calls(current_response)
                break
            current_response = follow_up
        except Exception as e:
            log.warning("Tool loop LLM callback failed: %s", e)
            current_response = strip_tool_calls(current_response)
            break

    # Strip any remaining tool-call markers
    final = strip_tool_calls(current_response)

    return ToolLoopOutput(
        final_response=final,
        tool_calls=all_tool_calls,
        rounds=rounds,
    )
