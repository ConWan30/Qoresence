"""PatternCoach — fail-closed spam / stick→R2 timing."""

from __future__ import annotations

from qoresence.foundry.pattern_coach import generate_pattern_report
from qoresence.mcp.server import TOOL_DEFS


def test_pattern_not_in_mcp_tools():
    assert "civif_coaching_report" not in {t["name"] for t in TOOL_DEFS}


def test_unbodied_empty():
    ev = [(i * 10_000_000, "square", "press", "c1") for i in range(20)]
    rep = generate_pattern_report(
        "p-un",
        events=ev,
        controller_bodied=False,
        board_locked=True,
        persist=False,
    )
    assert rep.coach_type == "pattern"
    assert rep.metrics == {}
    assert rep.issues == []


def test_unlocked_empty():
    ev = [(i * 10_000_000, "square", "press", "c1") for i in range(20)]
    rep = generate_pattern_report(
        "p-ul",
        events=ev,
        controller_bodied=True,
        board_locked=False,
        persist=False,
    )
    assert rep.metrics == {}
    assert rep.issues == []


def _spam_window(t0: int, clip: str, n: int = 10, gap: int = 50_000_000):
    return [(t0 + i * gap, "square", "press", clip) for i in range(n)]


def test_spam_windows_issue_and_clip_ids():
    ev = []
    ev.extend(_spam_window(0, "spam_a"))
    ev.extend(_spam_window(3_000_000_000, "spam_b"))
    ev.extend(_spam_window(6_000_000_000, "spam_c"))
    rep = generate_pattern_report("p-spam", events=ev, persist=False)
    assert rep.metrics["spam_windows_count"] == 3
    types = {i["type"] for i in rep.issues}
    assert "button_spam" in types
    clips = rep.issues[0]["clip_ids"]
    assert "spam_a" in clips
    assert "spam_b" in clips


def test_mistimed_combo_issue():
    ev = []
    for i in range(5):
        t = i * 2_000_000_000
        ev.append((t, "l3", "press", "combo_hi"))
        ev.append((t + 500_000_000, "r2", "press", "combo_hi"))
    rep = generate_pattern_report("p-combo", events=ev, persist=False)
    assert rep.metrics["mistimed_combo_count"] == 5
    assert any(i["type"] == "mistimed_combo" for i in rep.issues)
    assert "combo_hi" in rep.issues[-1]["clip_ids"]
