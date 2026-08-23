"""A2A policy + stub orchestrator tests (offline, no API keys)."""

from __future__ import annotations

from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
from qoresence.a2a.policy import A2APolicy
from qoresence.a2a.types import ChatProposal


def test_soft_vetoes_scoreline():
    t = _live_coupling_ticket()
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(text="Huge stop! 21-17 now!", path="fast", soft_only=True),
        situation={
            "home_score": 21,
            "away_score": 17,
            "coupling_ticket_id": t.ticket_id,
        },
    )
    assert r.__class__.__name__ == "Veto"
    assert "digit" in r.reason.lower() or "score" in r.reason.lower()


def _live_coupling_ticket():
    import time

    from qoresence.sync.coupling_ticket import (
        get_coupling_book,
        mint_coupling_ticket,
        reset_coupling_book,
    )

    reset_coupling_book()
    t = mint_coupling_ticket(
        clock_ns=time.monotonic_ns(),
        frame_seq=3,
        phrase="SPRINT",
        coupling=0.5,
        hold_energy=1.0,
        pll_lock=True,
        video_fresh=True,
    )
    get_coupling_book().put(t)
    return t


def test_soft_vetoes_without_coupling_ticket():
    from qoresence.sync.coupling_ticket import reset_coupling_book

    reset_coupling_book()
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(
            text="Pressure building — this possession matters.", path="fast", soft_only=True
        ),
        situation={"home_score": 31, "away_score": 38},
    )
    assert r.__class__.__name__ == "Veto"
    assert "coupling ticket" in r.reason.lower()


def test_soft_allows_no_digits():
    t = _live_coupling_ticket()
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(
            text="Pressure building — this possession matters.", path="fast", soft_only=True
        ),
        situation={
            "home_score": 31,
            "away_score": 38,
            "coupling_ticket_id": t.ticket_id,
        },
    )
    assert r.__class__.__name__ == "CommitAct"
    assert r.path == "fast"
    assert r.factual is False


def test_soft_vetoes_heat_without_ticket():
    from qoresence.sync.coupling_ticket import reset_coupling_book

    reset_coupling_book()
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(
            text="Controller heat on a live drive — eyes up.", path="fast", soft_only=True
        ),
        situation={"home_score": 31, "away_score": 38},
    )
    assert r.__class__.__name__ == "Veto"
    assert "coupling ticket" in r.reason.lower()


def test_soft_allows_heat_with_ticket():
    import time

    from qoresence.sync.coupling_ticket import (
        get_coupling_book,
        mint_coupling_ticket,
        reset_coupling_book,
    )

    reset_coupling_book()
    t = mint_coupling_ticket(
        clock_ns=time.monotonic_ns(),
        frame_seq=3,
        phrase="SPRINT",
        coupling=0.5,
        hold_energy=1.0,
        pll_lock=True,
        video_fresh=True,
    )
    get_coupling_book().put(t)
    p = A2APolicy(chat_cooldown_s=0)
    r = p.evaluate(
        ChatProposal(
            text="Controller heat on a live drive — eyes up.", path="fast", soft_only=True
        ),
        situation={"home_score": 31, "away_score": 38, "coupling_ticket_id": t.ticket_id},
    )
    assert r.__class__.__name__ == "CommitAct"


def test_confirm_digits_must_match_situation():
    p = A2APolicy(chat_cooldown_s=0)
    bad = p.evaluate(
        ChatProposal(text="Score update: 12-2", path="confirm", soft_only=False),
        situation={"home_score": 31, "away_score": 38},
    )
    assert bad.__class__.__name__ == "Veto"
    good = p.evaluate(
        ChatProposal(text="Score update: 31-38", path="confirm", soft_only=False),
        situation={"home_score": 31, "away_score": 38, "score_vlm_locked": True},
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
    t = _live_coupling_ticket()
    result = orch.run_cycle(
        situation={
            "game_state": "gameplay",
            "home_score": 31,
            "away_score": 38,
            "coupling_ticket_id": t.ticket_id,
        },
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


def test_menu_suppresses_video_ambient():
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    orch.maybe_trigger_from_drive(
        situation={"game_category": "football", "game_state": "menu"},
        reason="video_ambient",
    )
    import time

    time.sleep(0.15)
    assert called == []


def test_score_changed_reason_triggers():
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    t = _live_coupling_ticket()
    orch.maybe_trigger_from_drive(
        situation={
            "game_category": "football",
            "game_state": "gameplay",
            "home_score": 7,
            "away_score": 0,
            "score_vlm_locked": True,
            "coupling_ticket_id": t.ticket_id,
        },
        reason="score_changed",
    )
    import time

    time.sleep(0.25)
    assert called, "score_changed should schedule a commit"


def test_scene_tick_suppressed_without_pressure():
    """scene_tick should not fire on idle gameplay without drive phase/coupling/climax."""
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    orch.maybe_trigger_from_drive(
        situation={"game_category": "football", "game_state": "gameplay"},
        reason="scene_tick",
        coupling=0.1,
        drive_phase=None,
    )
    import time

    time.sleep(0.15)
    assert called == [], "scene_tick should be gated on pressure/coupling/must-fire"


def test_scene_tick_fires_with_pressure():
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    t = _live_coupling_ticket()
    orch.maybe_trigger_from_drive(
        situation={
            "game_category": "football",
            "game_state": "gameplay",
            "coupling_ticket_id": t.ticket_id,
        },
        reason="scene_tick",
        coupling=0.5,
        drive_phase="pressure",
    )
    import time

    time.sleep(0.25)
    assert called, "scene_tick should fire when drive phase is pressure"


def test_video_ambient_suppressed_without_pressure():
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    orch.maybe_trigger_from_drive(
        situation={"game_category": "football", "game_state": "gameplay"},
        reason="video_ambient",
        coupling=0.0,
        drive_phase=None,
    )
    import time

    time.sleep(0.15)
    assert called == [], "video_ambient should be gated on pressure/coupling/must-fire"


def test_video_ambient_fires_on_must_fire_climax():
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    t = _live_coupling_ticket()
    orch.maybe_trigger_from_drive(
        situation={
            "game_category": "football",
            "game_state": "gameplay",
            "last_outcome_event": "touchdown",
            "coupling_ticket_id": t.ticket_id,
        },
        reason="video_ambient",
        coupling=0.0,
        drive_phase=None,
    )
    import time

    time.sleep(0.25)
    assert called, "video_ambient should fire when must-fire predicate (big play) is true"


def test_coupling_reason_without_ticket_does_not_fire():
    from qoresence.sync.coupling_ticket import reset_coupling_book

    reset_a2a_orchestrator()
    reset_coupling_book()
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = []
    orch.on_commit = lambda c: called.append(c)
    orch.gemini.live = False
    orch.deepseek.live = False
    orch.policy.chat_cooldown_s = 0
    orch.maybe_trigger_from_drive(
        situation={"game_category": "football", "game_state": "gameplay"},
        reason="coupling",
        coupling=0.9,
    )
    import time

    time.sleep(0.15)
    assert called == []
    reset_a2a_orchestrator()


def test_near_duplicate_policy():
    p = A2APolicy(chat_cooldown_s=0)
    t = "Big moment energy — stay with it on this drive."
    ticket = _live_coupling_ticket()
    sit = {"coupling_ticket_id": ticket.ticket_id}
    r1 = p.evaluate(ChatProposal(text=t, path="fast", soft_only=True), situation=sit)
    assert r1.__class__.__name__ == "CommitAct"
    r2 = p.evaluate(
        ChatProposal(
            text="Big moment energy — stay with it on this drive!!", path="fast", soft_only=True
        ),
        situation=sit,
    )
    assert r2.__class__.__name__ == "Veto"
