"""DriveGraph unit tests (offline, synthetic timeline events)."""

from __future__ import annotations

from qoresence.agents.drive_graph import (
    DEFAULT_MAX_DRIVE_GRAPH_NODES,
    HARD_CEILING_DRIVE_GRAPH_NODES,
    DriveGraph,
    active_drive_graph,
    resolve_max_nodes,
)
from qoresence.agents.session_timeline import SessionTimeline, reset_session_timeline


def _ev(clock_ns: int, kind: str, path: str = "", message: str = "", coupling: float | None = None):
    return {
        "clock_ns": clock_ns,
        "kind": kind,
        "path": path,
        "message": message or kind,
        "coupling": coupling,
        "factual": path == "confirm",
    }


def test_phase_resolved_from_fast_arm_confirm():
    events = [
        _ev(1000, "fast_chat", "fast", "heat", 0.6),
        _ev(2000, "arm", "fast", "armed", 0.7),
        _ev(3000, "confirm_chat", "confirm", "score update", None),
        _ev(4000, "prediction_resolve", "confirm", "resolved", None),
    ]
    g = DriveGraph.from_events("d1", events)
    assert g.phase() == "resolved"
    assert g.climax_score()["score"] > 0.3
    assert g.climax_score()["has_fast_confirm"] is True


def test_climax_higher_with_fast_confirm_vs_cancel_only():
    good = DriveGraph.from_events(
        "g",
        [
            _ev(1, "fast_chat", "fast", "a", 0.8),
            _ev(2_000_000, "confirm_chat", "confirm", "b"),
            _ev(3_000_000, "prediction_resolve", "confirm", "r"),
        ],
    )
    bad = DriveGraph.from_events(
        "b",
        [
            _ev(1, "arm", "fast", "arm", 0.5),
            _ev(2_000_000, "prediction_cancel", "system", "ttl"),
        ],
    )
    assert good.climax_score()["score"] > bad.climax_score()["score"]


def test_match_fast_confirm_pairs():
    # lag 100ms within 8000ms
    events = [
        _ev(0, "fast_chat", "fast", "soft"),
        _ev(int(100e6), "confirm_chat", "confirm", "real"),
        _ev(int(200e6), "fast_clip", "fast", "clip"),
        _ev(int(300e6), "confirm_clip", "confirm", "clipc"),
    ]
    g = DriveGraph.from_events("m", events)
    pairs = g.match_fast_confirm(max_lag_ms=8000)
    assert len(pairs) >= 1
    assert pairs[0].lag_ms >= 0
    assert g.climax_score()["match_rate"] > 0


def test_ranked_chapter_nodes_sorted_limited():
    events = [_ev(i * 1000, "fast_chat", "fast", f"e{i}", 0.5) for i in range(12)]
    events.append(_ev(50_000, "prediction_resolve", "confirm", "end"))
    g = DriveGraph.from_events("c", events)
    ranked = g.ranked_chapter_nodes(k=5)
    assert len(ranked) <= 5
    times = [n.clock_ns for n in ranked]
    assert times == sorted(times)


def test_confirmed_td_outranks_t0_board():
    t0 = 0
    events = [
        _ev(t0, "fast_chat", "fast", "Live-board 0-0", 0.9),
        _ev(t0 + 10_000, "fast_chat", "fast", "board dump", 0.8),
        _ev(t0 + int(20e9), "confirm_score", "confirm", "touchdown 7-0"),
        _ev(t0 + int(21e9), "prediction_resolve", "confirm", "TD resolved"),
    ]
    g = DriveGraph.from_events("td", events)
    g.started_ns = t0
    ranked = g.ranked_chapter_nodes(k=3)
    labels = [n.label.lower() for n in ranked]
    assert any(
        "touchdown" in x or n.kind == "confirm_score" for n, x in zip(ranked, labels, strict=True)
    )
    cl = g.climax_score()
    assert cl["best_kind"] in {"confirm_score", "prediction_resolve"}
    assert "board" not in str(cl.get("best_label") or "").lower() or cl["best_kind"] != "fast_chat"


def test_rollback_marks_t0_board_stale():
    t0 = 1_000
    events = [
        _ev(t0, "fast_chat", "fast", "Live-board 14-0", 0.95),
        _ev(t0 + 50_000, "fast_chat", "fast", "board dump", 0.9),
        {
            **_ev(t0 + int(5e9), "score_rollback", "system", "rollback 14-0→7-0"),
            "payload": {"rollback": True},
        },
        _ev(t0 + int(12e9), "confirm_score", "confirm", "touchdown 14-7"),
    ]
    g = DriveGraph.from_events("rb", events)
    g.started_ns = t0
    g.mark_stale_after_rollback()
    assert any(n.stale_after_rollback for n in g.nodes if n.kind == "fast_chat")
    why = g.why_line() or ""
    assert "touchdown" in why.lower() or "confirm_score" in why.lower() or "14-7" in why
    ranked = g.ranked_chapter_nodes(k=4)
    top_kinds = [n.kind for n in ranked]
    assert "confirm_score" in top_kinds


def test_node_cap_keeps_tail_and_never_unbounded():
    events = [_ev(i + 1, "fast_chat", "fast", f"e{i}") for i in range(80)]
    g = DriveGraph.from_events("cap", events)
    assert g.node_cap == DEFAULT_MAX_DRIVE_GRAPH_NODES
    assert g.raw_node_count == 80
    assert g.nodes_truncated is True
    assert len(g.nodes) == DEFAULT_MAX_DRIVE_GRAPH_NODES
    assert g.nodes[0].message == "e32"
    assert g.nodes[-1].message == "e79"
    s = g.summary()
    assert s["node_count"] == 48
    assert s["nodes_truncated"] is True
    assert resolve_max_nodes(999) == HARD_CEILING_DRIVE_GRAPH_NODES
    tight = DriveGraph.from_events("cap8", events, max_nodes=8)
    assert len(tight.nodes) == 8
    assert tight.nodes_truncated is True


def test_empty_safe_summary():
    g = DriveGraph.from_events("empty", [])
    s = g.summary()
    assert s["phase"] == "empty"
    assert s["node_count"] == 0
    assert s["climax"]["score"] == 0.0
    assert g.why_line() is None


def test_from_timeline_drive_and_active_helper():
    reset_session_timeline()
    tl = SessionTimeline()
    t0 = 10_000_000_000
    tl.append(kind="arm", path="fast", message="arm", open_drive=True, clock_ns=t0, coupling=0.6)
    tl.append(kind="fast_chat", path="fast", message="heat", clock_ns=t0 + 1000)
    tl.append(
        kind="prediction_resolve",
        path="confirm",
        message="done",
        close_drive=True,
        clock_ns=t0 + 2000,
        factual=True,
    )
    drive = tl.drives()[-1]
    g = DriveGraph.from_timeline_drive(tl, drive)
    assert g is not None
    assert g.phase() in ("resolved", "active", "armed")
    # active is closed; helper uses last drive

    # bind singleton for helper
    import qoresence.agents.session_timeline as st

    st._timeline = tl
    ag = active_drive_graph(tl)
    assert ag is not None
    assert ag.summary()["drive_id"] == drive.drive_id
