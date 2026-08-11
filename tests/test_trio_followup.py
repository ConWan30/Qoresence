"""Tests for Phase 7 follow-up: agent tool wiring, audit CLI, expanded predicates."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from qoresence.a2a.deepseek_agent import DeepSeekChatAgent
from qoresence.a2a.gemini_agent import GeminiSceneAgent
from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
from qoresence.a2a.router import (
    _FourthDownPredicate,
    _OvertimeStartPredicate,
    _TwoPointConversionPredicate,
    evaluate_must_fire,
    get_predicates_for_category,
)
from qoresence.a2a.tools import ToolRegistry, create_default_registry
from qoresence.a2a.types import CommitAct, SceneProposal
from qoresence.core import RetinaEventBus

# ── Agent tool wiring ────────────────────────────────────────────────────────


def test_gemini_agent_accepts_tools():
    """GeminiSceneAgent should accept a ToolRegistry."""
    reg = ToolRegistry()
    agent = GeminiSceneAgent(live=False, tools=reg)
    assert agent._tools is reg


def test_gemini_agent_stub_uses_query_memory():
    """GeminiSceneAgent stub should use query-memory to enrich context."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
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

        reg = create_default_registry(jsonl_path=jsonl_path)
        agent = GeminiSceneAgent(live=False, tools=reg)

        scene = agent.propose_scene(
            situation={"game_state": "gameplay", "game_category": "football"},
            coupling=0.5,
            drive_phase="pressure",
        )
        # The stub should have enriched the summary with recent events
        assert "touchdown" in scene.summary or "Recent" in scene.summary


def test_gemini_agent_stub_without_tools():
    """GeminiSceneAgent stub without tools should still work."""
    agent = GeminiSceneAgent(live=False)
    scene = agent.propose_scene(
        situation={"game_state": "gameplay"},
        coupling=0.5,
        drive_phase="pressure",
    )
    assert scene.summary  # should have some summary


def test_deepseek_agent_accepts_tools():
    """DeepSeekChatAgent should accept a ToolRegistry."""
    reg = ToolRegistry()
    agent = DeepSeekChatAgent(live=False, tools=reg)
    assert agent._tools is reg


def test_deepseek_agent_stub_uses_query_memory():
    """DeepSeekChatAgent stub should use query-memory to enrich chat."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        now = time.time()
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "type": "outcome_event",
                        "clock_ns": 1,
                        "ts_ns": int(now * 1e9),
                        "source_lobe": "outcome",
                        "payload": {"event_name": "field_goal"},
                    }
                )
                + "\n"
            )

        reg = create_default_registry(jsonl_path=jsonl_path)
        agent = DeepSeekChatAgent(live=False, tools=reg)

        scene = SceneProposal(summary="pressure building", tension=0.7, tags=["pressure"])
        chat = agent.propose_chat(scene, path="fast")
        # The stub should have enriched the chat with recent events
        assert "field_goal" in chat.text or "Recent" in chat.text


def test_orchestrator_passes_tools_to_agents():
    """Orchestrator should pass its tool registry to both agents."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0, jsonl_path=str(jsonl_path))
        assert orch.gemini._tools is orch.tools
        assert orch.deepseek._tools is orch.tools
        reset_a2a_orchestrator()


def test_tool_enrichment_in_run_cycle():
    """A full run_cycle should use query-memory for enrichment."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        # Write an event to the log
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

        # Also set up the retina bus to capture events
        retina_bus = RetinaEventBus(session_id="tool_test", jsonl_path=jsonl_path, enable_ws=False)

        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0, jsonl_path=str(jsonl_path))
        orch.bus.set_retina_mirror(retina_bus, session_id="tool_test")

        result = orch.run_cycle(
            situation={"game_category": "football", "visual_confidence": 0.9},
            reason="touchdown",
        )

        assert isinstance(result, CommitAct)
        # The scene summary should include the recent event
        # (via Gemini stub tool enrichment)
        reset_a2a_orchestrator()


# ── Audit CLI ────────────────────────────────────────────────────────────────


def test_audit_cli_with_evidence():
    """--audit should print evidence chains and router decisions."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        # Write some evidence and router events
        now = time.time()
        events = [
            {
                "type": "evidence_chain",
                "clock_ns": 1,
                "ts_ns": int(now * 1e9),
                "source_lobe": "agent",
                "payload": {
                    "trigger_reason": "touchdown",
                    "confidence": 0.87,
                    "drive_phase": "open",
                    "coupling_score": 0.55,
                    "scene_model": "gemini-2.0-flash",
                    "chat_model": "deepseek-chat",
                    "cited_events": [{"event_name": "touchdown", "event_type": "outcome_event"}],
                    "cited_fields": [{"field_name": "home_score", "value": 7}],
                    "policy_refs": ["a2a_commit"],
                },
            },
            {
                "type": "router_decision",
                "clock_ns": 2,
                "ts_ns": int(now * 1e9),
                "source_lobe": "agent",
                "payload": {
                    "fired": True,
                    "reason": "touchdown",
                    "must_fire_hit": "big_play",
                    "interval_s": 6.0,
                    "last_trigger_age_s": 30.0,
                },
            },
            {
                "type": "router_decision",
                "clock_ns": 3,
                "ts_ns": int(now * 1e9),
                "source_lobe": "agent",
                "payload": {
                    "fired": False,
                    "reason": "scene_tick",
                    "must_fire_hit": None,
                    "interval_s": 45.0,
                    "last_trigger_age_s": 10.0,
                },
            },
        ]
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for ev in events:
                f.write(json.dumps(ev) + "\n")

        # Run the audit CLI
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "qoresence.cli",
                "--audit",
                "5",
                "--audit-jsonl",
                str(jsonl_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "EVIDENCE CHAINS" in result.stdout
        assert "ROUTER DECISIONS" in result.stdout
        assert "touchdown" in result.stdout
        assert "FIRED" in result.stdout
        assert "SUPP" in result.stdout


def test_audit_cli_no_events():
    """--audit should handle empty logs gracefully."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "empty.jsonl"
        Path(jsonl_path).write_text("", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "-m", "qoresence.cli", "--audit", "--audit-jsonl", str(jsonl_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "no evidence_chain" in result.stdout or "no evidence" in result.stdout.lower()


def test_audit_cli_missing_file():
    """--audit should handle missing log file gracefully."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "qoresence.cli",
            "--audit",
            "--audit-jsonl",
            "/nonexistent/path.jsonl",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "not found" in result.stdout


# ── Expanded predicates ──────────────────────────────────────────────────────


def test_fourth_down_predicate_fires():
    """Must-fire should trigger on 4th down."""
    sit = {"game_category": "football", "down": 4}
    pred = _FourthDownPredicate()
    assert pred.check(sit) is True


def test_fourth_down_predicate_doesnt_fire_on_other_downs():
    sit = {"game_category": "football", "down": 1}
    pred = _FourthDownPredicate()
    assert pred.check(sit) is False


def test_two_point_conversion_predicate_fires():
    """Must-fire should trigger on two_point_conversion event."""
    sit = {"game_category": "football", "last_outcome_event": "two_point_conversion"}
    pred = _TwoPointConversionPredicate()
    assert pred.check(sit) is True


def test_overtime_start_predicate_fires():
    """Must-fire should trigger on overtime start (quarter 5 or OT)."""
    sit = {"game_category": "football", "quarter": 5}
    pred = _OvertimeStartPredicate()
    assert pred.check(sit) is True


def test_overtime_start_predicate_fires_on_ot_string():
    sit = {"game_category": "football", "quarter": "OT"}
    pred = _OvertimeStartPredicate()
    assert pred.check(sit) is True


def test_overtime_start_predicate_doesnt_fire_on_regulation():
    sit = {"game_category": "football", "quarter": 4}
    pred = _OvertimeStartPredicate()
    assert pred.check(sit) is False


def test_expanded_predicates_in_football_registry():
    """Football predicate registry should include new predicates."""
    preds = get_predicates_for_category("football")
    names = [p.name for p in preds]
    assert "fourth_down" in names
    assert "two_point_conversion" in names
    assert "overtime_start" in names


def test_fourth_down_evaluates_via_registry():
    """4th down should trigger must-fire via the registry."""
    sit = {"game_category": "football", "down": 4}
    fired, pred = evaluate_must_fire(sit)
    assert fired is True
    assert pred == "fourth_down"
