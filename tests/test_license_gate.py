"""Phase 3 LicenseGate — no Quicksilver / A2A call without ticket_id."""

from __future__ import annotations

from qoresence.agents.chat_license import license_gate


def test_license_gate_refuses_empty_ticket_id():
    assert (
        license_gate(
            path="fast",
            ticket_id="",
            coupling_ticket=object(),
        )
        is False
    )


def test_license_gate_fast_needs_ticket_id_and_live_ticket():
    assert (
        license_gate(path="fast", ticket_id="c-1", coupling_ticket=object()) is True
    )
    assert license_gate(path="fast", ticket_id="c-1", coupling_ticket=None) is False


def test_license_gate_confirm_needs_ticket_id():
    assert (
        license_gate(
            path="confirm",
            ticket_id="",
            confirm_ticket=object(),
            score_vlm_locked=True,
        )
        is False
    )
    assert (
        license_gate(
            path="confirm",
            ticket_id="t-9",
            confirm_ticket=object(),
            score_vlm_locked=True,
        )
        is True
    )


def test_a2a_cycle_without_ticket_id_does_not_call_models():
    from qoresence.a2a.orchestrator import A2AOrchestrator, reset_a2a_orchestrator
    from qoresence.sync.coupling_ticket import reset_coupling_book

    reset_a2a_orchestrator()
    reset_coupling_book()
    orch = A2AOrchestrator(enabled=True, min_interval_s=0)
    called = {"gemini": 0, "deepseek": 0}
    orch.gemini.propose_scene = lambda **k: (_ for _ in ()).throw(AssertionError("QS"))
    orch.deepseek.propose_chat = lambda **k: (_ for _ in ()).throw(AssertionError("QS"))
    orch.gemini.live = True
    orch.deepseek.live = True

    def _g(**k):
        called["gemini"] += 1
        raise AssertionError("gemini must not run")

    def _d(**k):
        called["deepseek"] += 1
        raise AssertionError("deepseek must not run")

    orch.gemini.propose_scene = _g
    orch.deepseek.propose_chat = _d
    out = orch.run_cycle(situation={"game_state": "gameplay"}, path="fast")
    assert out is not None
    assert out.__class__.__name__ == "Veto"
    assert "license" in out.reason.lower() or "ticket" in out.reason.lower()
    assert called["gemini"] == 0
    assert called["deepseek"] == 0
    reset_a2a_orchestrator()
