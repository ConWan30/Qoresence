"""A2A policy + stub orchestrator tests (offline, no API keys)."""

from __future__ import annotations

from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
from qoresence.a2a.policy import A2APolicy
from qoresence.a2a.types import ChatProposal


def test_soft_vetoes_scoreline():
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(text="Huge stop! 21-17 now!", path="fast", soft_only=True),
        situation={"home_score": 21, "away_score": 17},
    )
    assert r.__class__.__name__ == "Veto"
    assert "digit" in r.reason.lower() or "score" in r.reason.lower()


def test_soft_allows_no_digits():
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(text="Controller heat on a live drive — eyes up.", path="fast", soft_only=True),
        situation={"home_score": 31, "away_score": 38},
    )
    assert r.__class__.__name__ == "CommitAct"
    assert r.path == "fast"
    assert r.factual is False


def test_confirm_digits_must_match_situation():
    p = A2APolicy(chat_cooldown_s=0)
    bad = p.evaluate(
        ChatProposal(text="Score update: 12-2", path="confirm", soft_only=False),
        situation={"home_score": 31, "away_score": 38},
    )
    assert bad.__class__.__name__ == "Veto"
    good = p.evaluate(
        ChatProposal(text="Score update: 31-38", path="confirm", soft_only=False),
        situation={"home_score": 31, "away_score": 38},
    )
    assert good.__class__.__name__ == "CommitAct"
    assert good.factual is True


def test_stub_cycle_produces_commit_without_api():
    reset_a2a_orchestrator()
    commits: list = []
    orch = A2AOrchestrator(
        enabled=True,
        min_interval_s=0,
        on_commit=lambda c: commits.append(c),
    )
    # Force stub agents
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    result = orch.run_cycle(
        situation={"game_state": "gameplay", "home_score": 31, "away_score": 38},
        coupling=0.7,
        drive_phase="pressure",
        path="fast",
    )
    assert result is not None
    assert result.__class__.__name__ == "CommitAct"
    assert commits
    # Soft commit must not invent 31-38 scoreline
    assert "31-38" not in commits[0].text
    assert "21-17" not in commits[0].text


def test_disabled_orchestrator_no_auto_trigger():
    orch = A2AOrchestrator(enabled=False, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.maybe_trigger_from_drive(coupling=0.9, drive_phase="armed")
    import time

    time.sleep(0.15)
    assert called == []
