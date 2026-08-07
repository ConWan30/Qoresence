"""SessionTimeline unit tests (offline)."""

from __future__ import annotations

from qoresence.agents.session_timeline import SessionTimeline, reset_session_timeline


def test_append_recent_ordering():
    tl = SessionTimeline()
    tl.append(kind="a", path="fast", message="one", clock_ns=100)
    tl.append(kind="b", path="confirm", message="two", clock_ns=200)
    recent = tl.recent(10)
    assert len(recent) == 2
    assert recent[0].kind == "a"
    assert recent[1].kind == "b"
    assert recent[-1].message == "two"


def test_why_last():
    tl = SessionTimeline()
    assert tl.why_last() is None
    tl.append(
        kind="fast_chat",
        path="fast",
        message="soft heat",
        coupling=0.71,
        buttons=["r1", "cross"],
        frame_seq=18422,
        factual=False,
        clock_ns=1,
    )
    why = tl.why_last()
    assert why is not None
    assert why["path"] == "fast"
    assert "0.71" in why["line"]
    assert "soft heat" in why["line"]
    assert "18422" in why["line"]


def test_drive_open_close():
    tl = SessionTimeline()
    tl.append(kind="arm", path="fast", open_drive=True, clock_ns=10, drive_context={"rz": True})
    assert tl.active_drive() is not None
    did = tl.active_drive().drive_id
    tl.append(kind="fast_chat", path="fast", clock_ns=20)
    tl.append(kind="confirm_score", path="confirm", close_drive=True, clock_ns=30, factual=True)
    assert tl.active_drive() is None
    drives = tl.drives()
    assert len(drives) == 1
    assert drives[0].drive_id == did
    assert drives[0].ended_ns == 30
    assert len(drives[0].event_indices) >= 2


def test_snapshot_and_singleton():
    reset_session_timeline()
    from qoresence.agents.session_timeline import get_session_timeline

    tl = get_session_timeline()
    tl.append(kind="x", path="confirm", message="ok", clock_ns=5)
    snap = tl.snapshot()
    assert snap["why_last"] is not None
    assert snap["count"] >= 1


def test_snapshot_includes_drive_graph():
    reset_session_timeline()
    from qoresence.agents.session_timeline import get_session_timeline

    tl = get_session_timeline()
    t0 = 50_000_000_000
    tl.append(kind="arm", path="fast", message="arm", open_drive=True, clock_ns=t0, coupling=0.7)
    tl.append(kind="fast_chat", path="fast", message="heat", clock_ns=t0 + 1000, coupling=0.8)
    tl.append(
        kind="confirm_chat",
        path="confirm",
        message="score",
        clock_ns=t0 + 2_000_000,
        factual=True,
    )
    snap = tl.snapshot()
    assert snap.get("drive_graph") is not None
    assert snap["drive_graph"]["phase"] in (
        "armed",
        "pressure",
        "active",
        "resolved",
        "open",
    )
    assert "climax" in snap["drive_graph"]
    assert snap["why_last"] is not None
