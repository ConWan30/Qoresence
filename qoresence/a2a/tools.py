"""Typed tool registry for A2A agents (Trio Principle 3).

Defines a tool registry that allows the reasoning tier (Gemini/DeepSeek)
to re-query lower tiers with refined parameters. Each tool has a strict
JSON schema and returns a structured object.

Tools implemented:
- query-memory: Filter the JSONL event log by type, time range, fields
- zoom-redetect: Request a cropped region re-analysis from the visual lobe
  (requires a callback channel; falls back to no-op if not wired)

The depth bound (K=3) limits tool calls per reasoning cycle.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)

# Maximum tool calls per reasoning cycle (Trio P3 depth bound)
MAX_TOOL_DEPTH = 3


# ──────────────────────────────────────────────────────────────────────────────
# TOOL PROTOCOL AND REGISTRY
# ──────────────────────────────────────────────────────────────────────────────


class ToolHandler(Protocol):
    """Callable that executes a tool and returns a structured result."""

    def __call__(self, **params: Any) -> dict[str, Any]: ...


@dataclass
class ToolDef:
    """Definition of a tool available to the reasoning tier."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for parameters
    handler: ToolHandler

    def to_dict(self) -> dict[str, Any]:
        """Serialize for inclusion in LLM prompts (without handler)."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Registry of tools available to the A2A reasoning tier.

    Tools are registered with a name, JSON schema, and handler function.
    The registry enforces a depth bound (MAX_TOOL_DEPTH) per cycle.
    """

    def __init__(self, max_depth: int = MAX_TOOL_DEPTH) -> None:
        self._tools: dict[str, ToolDef] = {}
        self._max_depth = max_depth
        self._call_count = 0

    def register(self, tool: ToolDef) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool
        log.debug("Tool registered: %s", tool.name)

    def get(self, name: str) -> ToolDef | None:
        """Get a tool definition by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        """List all registered tools (for LLM prompt inclusion)."""
        return [t.to_dict() for t in self._tools.values()]

    def call(self, name: str, **params: Any) -> dict[str, Any]:
        """Execute a tool by name with the given parameters.

        Returns the tool's structured result, or an error dict if the
        tool is not found or the depth bound is exceeded.
        """
        if self._call_count >= self._max_depth:
            return {"error": "depth_bound_exceeded", "max_depth": self._max_depth}

        tool = self._tools.get(name)
        if tool is None:
            return {"error": "tool_not_found", "name": name}

        self._call_count += 1
        try:
            result = tool.handler(**params)
            if not isinstance(result, dict):
                return {"error": "invalid_return_type", "name": name}
            return result
        except Exception as e:
            log.warning("Tool %s failed: %s", name, e)
            return {"error": "tool_execution_failed", "name": name, "detail": str(e)}

    def reset_depth(self) -> None:
        """Reset the call counter for a new reasoning cycle."""
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    @property
    def max_depth(self) -> int:
        return self._max_depth


# ──────────────────────────────────────────────────────────────────────────────
# BUILT-IN TOOL: query-memory
# ──────────────────────────────────────────────────────────────────────────────


def make_query_memory_tool(jsonl_path: Path | str) -> ToolDef:
    """Create a query-memory tool that searches the JSONL event log.

    Parameters:
        event_type: Filter by event type (e.g., "outcome_event")
        event_name: Filter by event_name in payload (for outcome events)
        seconds_back: How far back to search (default 300s = 5 min)
        limit: Maximum number of results (default 20)

    Returns:
        dict with "events" list and "count"
    """
    jsonl_path = Path(jsonl_path)

    def handler(
        event_type: str | None = None,
        event_name: str | None = None,
        seconds_back: float = 300.0,
        limit: int = 20,
    ) -> dict[str, Any]:
        if not jsonl_path.exists():
            return {"events": [], "count": 0, "error": "log_not_found"}

        cutoff = time.time() - seconds_back
        results: list[dict[str, Any]] = []

        try:
            # Read lines (tail for efficiency on large logs)
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        except Exception as e:
            return {"events": [], "count": 0, "error": str(e)}

        for line in reversed(lines):  # most recent first
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            # Filter by event type
            if event_type and ev.get("type") != event_type:
                continue

            # Filter by event_name (for outcome events)
            if event_name:
                payload = ev.get("payload") or {}
                if payload.get("event_name") != event_name:
                    continue

            # Filter by time (ts_ns is wall-clock nanoseconds)
            ts_ns = ev.get("ts_ns")
            if ts_ns is not None:
                ev_time = ts_ns / 1e9
                if ev_time < cutoff:
                    continue

            results.append({
                "type": ev.get("type"),
                "clock_ns": ev.get("clock_ns"),
                "source_lobe": ev.get("source_lobe"),
                "payload": ev.get("payload"),
            })

            if len(results) >= limit:
                break

        return {"events": results, "count": len(results)}

    return ToolDef(
        name="query-memory",
        description="Search the event log for recent events by type, name, or time range.",
        parameters={
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "description": "Filter by event type (e.g., 'outcome_event', 'visual_context')",
                },
                "event_name": {
                    "type": "string",
                    "description": "Filter by event_name in payload (for outcome events)",
                },
                "seconds_back": {
                    "type": "number",
                    "description": "How far back to search in seconds (default 300)",
                    "default": 300,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 20)",
                    "default": 20,
                },
            },
        },
        handler=handler,
    )


# ──────────────────────────────────────────────────────────────────────────────
# BUILT-IN TOOL: zoom-redetect
# ──────────────────────────────────────────────────────────────────────────────


# Type for the zoom-redetect callback: (region, vocabulary) -> detection result
ZoomRedetectCallback = Callable[[str, list[str]], dict[str, Any]]


def make_zoom_redetect_tool(callback: ZoomRedetectCallback | None = None) -> ToolDef:
    """Create a zoom-redetect tool for region-refined visual analysis.

    Parameters:
        region: Bounding box description (e.g., "top-left", "scoreboard", "0,0,100,100")
        vocabulary: Refined class vocabulary to look for

    Returns:
        dict with "detections" list and "region"

    If no callback is wired, returns a no-op result.
    """

    def handler(
        region: str = "full",
        vocabulary: list[str] | None = None,
    ) -> dict[str, Any]:
        if callback is None:
            return {
                "detections": [],
                "region": region,
                "error": "no_callback_wired",
                "message": "zoom-redetect not available (no visual lobe callback)",
            }

        try:
            result = callback(region, vocabulary or [])
            if not isinstance(result, dict):
                return {"error": "invalid_callback_return", "region": region}
            return {"detections": result.get("detections", []), "region": region, **result}
        except Exception as e:
            return {"error": "callback_failed", "region": region, "detail": str(e)}

    return ToolDef(
        name="zoom-redetect",
        description="Re-analyze a specific screen region with a refined vocabulary.",
        parameters={
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "Region to analyze: 'top-left', 'scoreboard', 'bottom-right', or 'x,y,w,h'",
                },
                "vocabulary": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Refined class vocabulary to look for",
                },
            },
            "required": ["region"],
        },
        handler=handler,
    )


# ──────────────────────────────────────────────────────────────────────────────
# FACTORY: Default registry
# ──────────────────────────────────────────────────────────────────────────────


def create_default_registry(
    jsonl_path: Path | str | None = None,
    zoom_callback: ZoomRedetectCallback | None = None,
) -> ToolRegistry:
    """Create a ToolRegistry with the default built-in tools.

    Args:
        jsonl_path: Path to the JSONL event log (for query-memory)
        zoom_callback: Optional callback for zoom-redetect

    Returns:
        ToolRegistry with query-memory and optionally zoom-redetect
    """
    registry = ToolRegistry()
    if jsonl_path:
        registry.register(make_query_memory_tool(jsonl_path))
    registry.register(make_zoom_redetect_tool(zoom_callback))
    return registry
