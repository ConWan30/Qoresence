"""Tests for Phase 7.1: Evidence chains (Trio Principle 4).

Verifies that the A2A orchestrator builds and attaches structured
evidence chains to every CommitAct, and emits EVIDENCE_CHAIN events
to the RetinaEventBus.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
from qoresence.a2a.types import (
    CommitAct,
    EventRef,
    EvidenceChain,
    FieldProvenance,
)
from qoresence.core import RetinaEventBus

# ── EvidenceChain dataclass ──────────────────────────────────────────────────


def test_evidence_chain_to_dict():
    """EvidenceChain should serialize to dict with all fields."""
    ec = EvidenceChain(
        cited_events=[EventRef("outcome_event", 123, "outcome", "touchdown", "TD")],
        cited_fields=[FieldProvenance("home_score", 7, "vlm", 0.9, "abc123", "gemini")],
        coupling_score=0.65,
        drive_phase="pressure",
        trigger_reason="touchdown",
        scene_model="gemini-2.0-flash",
        chat_model="deepseek-chat",
        confidence=0.87,
        policy_refs=["a2a_commit"],
    )
    d = ec.to_dict()
    assert d["trigger_reason"] == "touchdown"
    assert d["confidence"] == 0.87
    assert len(d["cited_events"]) == 1
    assert d["cited_events"][0]["event_name"] == "touchdown"
    assert len(d["cited_fields"]) == 1
    assert d["cited_fields"][0]["field_name"] == "home_score"
    assert d["cited_fields"][0]["value"] == 7


def test_evidence_chain_empty_defaults():
    """Empty EvidenceChain should have safe defaults."""
    ec = EvidenceChain()
    d = ec.to_dict()
    assert d["cited_events"] == []
    assert d["cited_fields"] == []
    assert d["confidence"] == 0.0
    assert d["trigger_reason"] == ""


def test_commit_act_has_evidence_field():
    """CommitAct should have an evidence field."""
    act = CommitAct(action="chat", text="test", evidence={"confidence": 0.9})
    assert act.evidence is not None
    assert act.evidence["confidence"] == 0.9


def test_commit_act_evidence_defaults_none():
    """CommitAct evidence should default to None."""
    act = CommitAct(action="chat", text="test")
    assert act.evidence is None


# ── Orchestrator evidence building ───────────────────────────────────────────


def test_evidence_chain_built_on_commit():
    """A committed A2A cycle should produce an evidence chain."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        retina_bus = RetinaEventBus(session_id="ev_test", jsonl_path=jsonl_path, enable_ws=False)

        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(retina_bus, session_id="ev_test")

        situation = {
            "game_state": "gameplay",
            "game_category": "football",
            "game_title": "NCAA College Football 27",
            "home_score": 14,
            "away_score": 7,
            "quarter": 2,
            "down": 3,
            "field_position": "opp 15",
            "possession": "home",
            "game_clock_seconds": 115,
            "visual_confidence": 0.92,
            "controller_apm": 45,
            "presence_sync_ok": True,
            "last_outcome_event": "red_zone_entry",
        }

        result = orch.run_cycle(
            situation=situation,
            coupling=0.55,
            drive_phase="pressure",
            reason="red_zone_entry",
            path="fast",
        )

        # Should be a CommitAct (stubs always commit)
        assert isinstance(result, CommitAct), f"Expected CommitAct, got {type(result)}"
        assert result.evidence is not None, "Evidence chain not attached to CommitAct"

        ev = result.evidence
        assert ev["trigger_reason"] == "red_zone_entry"
        assert ev["coupling_score"] == 0.55
        assert ev["drive_phase"] == "pressure"
        assert ev["confidence"] > 0.0

        # Should cite the last outcome event
        event_names = [e["event_name"] for e in ev["cited_events"] if e.get("event_name")]
        assert "red_zone_entry" in event_names

        # Should cite football fields
        field_names = [f["field_name"] for f in ev["cited_fields"]]
        assert "home_score" in field_names
        assert "quarter" in field_names
        assert "field_position" in field_names

        # Should cite controller APM
        apm_fields = [f for f in ev["cited_fields"] if f["field_name"] == "controller_apm"]
        assert len(apm_fields) == 1
        assert apm_fields[0]["value"] == 45
        assert apm_fields[0]["source"] == "controller"

        # Should cite presence sync
        presence_fields = [f for f in ev["cited_fields"] if f["field_name"] == "presence_sync_ok"]
        assert len(presence_fields) == 1
        assert presence_fields[0]["source"] == "fusion"

        retina_bus.close()
        reset_a2a_orchestrator()


def test_evidence_chain_emitted_to_retina_bus():
    """An EVIDENCE_CHAIN event should be emitted to the RetinaEventBus."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        retina_bus = RetinaEventBus(session_id="ev_emit", jsonl_path=jsonl_path, enable_ws=False)

        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(retina_bus, session_id="ev_emit")

        situation = {
            "game_state": "gameplay",
            "game_category": "football",
            "home_score": 21,
            "away_score": 14,
            "quarter": 4,
            "visual_confidence": 0.88,
            "last_outcome_event": "touchdown",
        }

        result = orch.run_cycle(
            situation=situation,
            coupling=0.60,
            drive_phase="open",
            reason="touchdown",
        )

        assert isinstance(result, CommitAct)

        # Read events from JSONL
        lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line) for line in lines if line.strip()]

        # Should have an evidence_chain event
        ev_events = [e for e in events if e["type"] == "evidence_chain"]
        assert len(ev_events) >= 1, "No evidence_chain event emitted"

        ev_payload = ev_events[0]["payload"]
        assert ev_payload["trigger_reason"] == "touchdown"
        assert ev_payload["confidence"] > 0.0

        retina_bus.close()
        reset_a2a_orchestrator()


def test_evidence_chain_shooter_fields():
    """Evidence chain should cite shooter fields for shooter games."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)

    situation = {
        "game_state": "gameplay",
        "game_category": "shooter",
        "game_title": "Call of Duty",
        "kills": 15,
        "deaths": 3,
        "score": 2500,
        "health": 80,
        "ammo": 30,
        "visual_confidence": 0.85,
    }

    result = orch.run_cycle(
        situation=situation,
        coupling=0.50,
        drive_phase="active",
        reason="coupling",
    )

    assert isinstance(result, CommitAct)
    ev = result.evidence
    field_names = [f["field_name"] for f in ev["cited_fields"]]
    assert "kills" in field_names
    assert "deaths" in field_names
    assert "score" in field_names
    assert "health" in field_names

    reset_a2a_orchestrator()


def test_evidence_chain_confidence_blend():
    """Confidence should be a blend of visual confidence and scene tension."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)

    situation = {
        "game_state": "gameplay",
        "game_category": "football",
        "visual_confidence": 1.0,  # max visual confidence
    }

    result = orch.run_cycle(
        situation=situation,
        coupling=0.5,
        reason="scene_tick",
    )

    assert isinstance(result, CommitAct)
    ev = result.evidence
    # With vis_conf=1.0 and stub tension=0.5: 1.0*0.6 + 0.5*0.4 = 0.8
    assert 0.5 <= ev["confidence"] <= 1.0

    reset_a2a_orchestrator()


def test_evidence_chain_no_crash_on_empty_situation():
    """Evidence chain building should not crash on an empty situation."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)

    result = orch.run_cycle(
        situation={},
        coupling=None,
        drive_phase=None,
        reason="force",
    )

    # Should still produce a CommitAct with an evidence chain
    assert isinstance(result, CommitAct)
    assert result.evidence is not None
    assert result.evidence["cited_events"] == []
    assert result.evidence["cited_fields"] == []

    reset_a2a_orchestrator()


def test_evidence_chain_in_agent_action_mirror():
    """The AGENT_ACTION event mirrored to RetinaEventBus should include evidence."""
    with tempfile.TemporaryDirectory() as td:
        jsonl_path = Path(td) / "events.jsonl"
        retina_bus = RetinaEventBus(
            session_id="mirror_test", jsonl_path=jsonl_path, enable_ws=False
        )

        orch = A2AOrchestrator(enabled=True, min_interval_s=0.0)
        orch.bus.set_retina_mirror(retina_bus, session_id="mirror_test")

        situation = {
            "game_state": "gameplay",
            "game_category": "football",
            "home_score": 7,
            "visual_confidence": 0.9,
        }

        result = orch.run_cycle(situation=situation, reason="score_changed")

        assert isinstance(result, CommitAct)

        # Read AGENT_ACTION events
        lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line) for line in lines if line.strip()]
        agent_events = [e for e in events if e["type"] == "agent_action"]

        assert len(agent_events) >= 1
        # The AGENT_ACTION payload should include evidence
        assert "evidence" in agent_events[0]["payload"]
        assert agent_events[0]["payload"]["evidence"] is not None

        retina_bus.close()
        reset_a2a_orchestrator()
