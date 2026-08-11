"""Bounded synthetic soak — timeline + A2A policy + DriveGraph under load."""

from __future__ import annotations

import time

from qoresence.a2a.orchestrator import A2AOrchestrator
from qoresence.agents.drive_graph import DriveGraph
from qoresence.agents.session_timeline import SessionTimeline, reset_session_timeline
from qoresence.observability import get_latency_stats, record_latency, reset_latency_stats


def test_latency_stats_disabled_summary():
    reset_latency_stats(enabled=False)
    st = get_latency_stats()
    assert st.enabled is False
    s = st.summary()
    assert s["enabled"] is False
    assert s["names"] == {}
    # record is no-op
    record_latency("noop", 1.5)
    assert st.summary()["names"] == {}


def test_latency_stats_enabled_records():
    reset_latency_stats(enabled=True)
    st = get_latency_stats()
    for i in range(10):
        record_latency("ivc_tick", 1.0 + i * 0.1, frame_seq=i)
    s = st.summary()
    assert s["enabled"] is True
    assert "ivc_tick" in s["names"]
    assert s["names"]["ivc_tick"]["count"] >= 10
    assert s["names"]["ivc_tick"]["p50_ms"] >= 1.0


def test_synthetic_soak_timeline_and_graph():
    """~200 synthetic events: timeline + graph stay bounded and coherent."""
    reset_session_timeline()
    tl = SessionTimeline()
    t0 = time.monotonic_ns()
    tl.append(kind="arm", path="fast", open_drive=True, clock_ns=t0, coupling=0.6)
    for i in range(200):
        path = "fast" if i % 3 else "confirm"
        kind = "fast_chat" if path == "fast" else "confirm_chat"
        tl.append(
            kind=kind,
            path=path,
            message=f"m{i}",
            clock_ns=t0 + i * 1_000_000,
            coupling=0.4 + (i % 5) * 0.05,
            factual=(path == "confirm"),
        )
    tl.append(
        kind="prediction_resolve",
        path="confirm",
        close_drive=True,
        clock_ns=t0 + 250_000_000,
        factual=True,
    )
    snap = tl.snapshot(recent_n=50)
    assert snap["count"] <= 50
    assert snap["why_last"] is not None
    drive = tl.drives()[-1]
    g = DriveGraph.from_timeline_drive(tl, drive)
    assert g is not None
    assert g.phase() in ("resolved", "active", "pressure", "armed", "open", "cancelled")
    s = g.summary()
    assert "climax" in s
    assert s["node_count"] >= 1


def test_a2a_stub_soak_under_policy():
    commits = []
    orch = A2AOrchestrator(enabled=True, min_interval_s=0, on_commit=lambda c: commits.append(c))
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    for _i in range(15):
        r = orch.run_cycle(
            situation={"home_score": 31, "away_score": 38, "game_state": "gameplay"},
            coupling=0.6,
            drive_phase="pressure",
            path="fast",
        )
        # After first commit, cooldown disabled so may still commit or veto duplicate
        assert r is not None
    # Soft path must never invent scoreline
    for c in commits:
        assert "31-38" not in c.text
        assert "21-17" not in c.text
