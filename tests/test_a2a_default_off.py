"""QorGraph #5 — a2a-reentrancy-default-off principle gates."""

from __future__ import annotations

import inspect
from argparse import Namespace
from pathlib import Path


def test_clutchbot_a2a_default_off():
    from qoresence.core.unified_config import ClutchBotConfig

    assert ClutchBotConfig().a2a_enabled is False


def test_from_env_a2a_opt_in(monkeypatch):
    from qoresence.core.unified_config import RetinaUnifiedConfig

    monkeypatch.delenv("QORESENCE_A2A", raising=False)
    off = RetinaUnifiedConfig.from_env()
    assert off.clutchbot.a2a_enabled is False

    monkeypatch.setenv("QORESENCE_A2A", "1")
    on = RetinaUnifiedConfig.from_env()
    assert on.clutchbot.a2a_enabled is True


def test_play_does_not_enable_a2a():
    """--play alone must not flip A2A on (flag/env remain opt-in)."""
    from qoresence.core.unified_config import ClutchBotConfig, RetinaUnifiedConfig

    cfg = RetinaUnifiedConfig(session_id="s", session_head_ns=1)
    assert cfg.clutchbot.a2a_enabled is False
    args = Namespace(play=True, a2a=False)
    enabled = bool(getattr(args, "a2a", False) or cfg.clutchbot.a2a_enabled)
    assert enabled is False
    # play must not mutate clutchbot default
    assert ClutchBotConfig().a2a_enabled is False


def test_in_trigger_guard_present():
    from qoresence.a2a import orchestrator as orch

    src = inspect.getsource(orch.A2AOrchestrator)
    assert "in_trigger" in src
    assert "_tls" in src


def test_deadlock_regression_tests_not_deleted():
    text = Path("tests/test_deadlock_regression.py").read_text(encoding="utf-8")
    for name in (
        "test_reentrant_trigger_from_router_decision_does_not_deadlock",
        "test_suppressed_trigger_emits_outside_lock",
        "test_presence_lock_released_during_report_fanout",
        "test_full_cascade_streamer_event_with_a2a_loop",
    ):
        assert f"def {name}" in text, name


def test_play_help_states_a2a_society_stay_off():
    # Avoid importing qoresence.cli (heavy vision deps); assert source help text.
    text = Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "A2A/Society stay OFF unless --a2a / --agent-society." in text
