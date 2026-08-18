"""A2A policy tuning — fewer vetoes, more meaningful chat."""

from __future__ import annotations

import time

from qoresence.a2a.policy import A2APolicy
from qoresence.a2a.types import ChatProposal


def _soft(text: str) -> ChatProposal:
    return ChatProposal(text=text, path="fast", soft_only=True, model="test")


def test_cooldown_lowered_from_45s():
    """Default cooldown should be 25s, not the old 45s."""
    # Reset env to default
    import os
    os.environ.pop("QORESENCE_A2A_CHAT_COOLDOWN_S", None)
    os.environ.pop("QORESENCE_A2A_DUPLICATE_WINDOW_S", None)
    p = A2APolicy()
    assert p.chat_cooldown_s == 25.0
    assert p.duplicate_window_s == 120.0


def test_natural_commentary_not_vetoed():
    """'Gained 12 yards on that carry' should NOT be vetoed for inventing digits."""
    p = A2APolicy()
    p._last_commit_ts = 0.0  # bypass cooldown
    result = p.evaluate(
        _soft("Gained 12 yards on that carry — nice run."),
        situation={"home_score": 17, "away_score": 14},
    )
    # Should be accepted (CommitAct), not Veto
    assert not hasattr(result, "rejected_text"), f"Unexpectedly vetoed: {result}"


def test_explicit_scoreline_still_vetoed_in_soft():
    """'31-38 game' should still be vetoed in soft path (explicit scoreline)."""
    p = A2APolicy()
    p._last_commit_ts = 0.0
    result = p.evaluate(
        _soft("Looking at a 31-38 game here"),
        situation={"home_score": 17, "away_score": 14},
    )
    assert hasattr(result, "rejected_text"), "Scoreline should be vetoed in soft path"


def test_near_duplicate_requires_40_char_match():
    """Two chats sharing only 24 chars should NOT be near-duplicate."""
    p = A2APolicy()
    # First chat
    p._last_commit_ts = 0.0
    r1 = p.evaluate(
        _soft("Pressure building on this drive — defense stepping up now"),
        situation={},
    )
    assert not hasattr(r1, "rejected_text")
    # Reset cooldown to test near-duplicate, not cooldown
    p._last_commit_ts = 0.0
    # Second chat shares prefix "pressure building on this d" (24 chars) but not 40
    r2 = p.evaluate(
        _soft("Pressure building on this drive — offense looking sharp"),
        situation={},
    )
    assert not hasattr(r2, "rejected_text"), (
        f"24-char prefix match should not veto, got: {getattr(r2, 'reason', '?')}"
    )


def test_cooldown_env_override():
    """QORESENCE_A2A_CHAT_COOLDOWN_S should override default."""
    import os
    old = os.environ.get("QORESENCE_A2A_CHAT_COOLDOWN_S")
    try:
        os.environ["QORESENCE_A2A_CHAT_COOLDOWN_S"] = "60.0"
        p = A2APolicy()
        assert p.chat_cooldown_s == 60.0
    finally:
        if old is None:
            os.environ.pop("QORESENCE_A2A_CHAT_COOLDOWN_S", None)
        else:
            os.environ["QORESENCE_A2A_CHAT_COOLDOWN_S"] = old
