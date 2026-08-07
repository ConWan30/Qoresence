"""DriveGraph unit tests (offline, synthetic timeline events)."""

from __future__ import annotations

from qoresence.agents.drive_graph import DriveGraph, active_drive_graph
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
    events = [
        _ev(i * 1000, "fast_chat", "fast", f"e{i}", 0.5)
        for i in range(12)
    ]
    events.append(_ev(50_000, "prediction_resolve", "confirm", "end"))
    g = DriveGraph.from_events("c", events)
    ranked = g.ranked_chapter_nodes(k=5)
    assert len(ranked) <= 5
    times = [n.clock_ns for n in ranked]
    assert times == sorted(times)


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
    from qoresence.agents.session_timeline import get_session_timeline

    # bind singleton for helper
    import qoresence.agents.session_timeline as st

    st._timeline = tl
    ag = active_drive_graph(tl)
    assert ag is not None
    assert ag.summary()["drive_id"] == drive.drive_id
