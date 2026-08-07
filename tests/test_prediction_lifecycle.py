"""Prediction lifecycle unit tests (offline, no Helix)."""

from __future__ import annotations

import time

from qoresence.agents.prediction_lifecycle import (
    PredictionLifecycleManager,
    PredictionState,
    reset_prediction_lifecycle,
)
from qoresence.agents.session_timeline import reset_session_timeline


def test_arm_ttl_cancel():
    from qoresence.agents.session_timeline import get_session_timeline

    reset_session_timeline()
    m = PredictionLifecycleManager(arm_ttl_s=0.05)
    m.arm(coupling=0.6, reason="test arm")
    assert m.state == PredictionState.ARMED
    time.sleep(0.08)
    st = m.tick(coupling=0.1, still_pressure_context=True)
    assert st == PredictionState.IDLE  # cancel → reset soft → idle
    kinds = [e.kind for e in get_session_timeline().recent(20)]
    assert "arm" in kinds
    assert "prediction_cancel" in kinds


def test_arm_resolve_without_open():
    reset_session_timeline()
    m = PredictionLifecycleManager()
    m.arm(coupling=0.7, frame_seq=9)
    assert m.state == PredictionState.ARMED
    m.resolve(0, reason="score_changed")
    assert m.state == PredictionState.IDLE
    from qoresence.agents.session_timeline import get_session_timeline

    kinds = [e.kind for e in get_session_timeline().recent(20)]
    assert "arm" in kinds
    assert "prediction_resolve" in kinds


def test_timeline_receives_open():
    reset_session_timeline()
    m = PredictionLifecycleManager(open_on_arm=False)
    m.arm(coupling=0.9)
    m.try_open(coupling=0.9, force=True)
    assert m.state == PredictionState.OPEN
    from qoresence.agents.session_timeline import get_session_timeline

    kinds = [e.kind for e in get_session_timeline().recent(20)]
    assert "prediction_open" in kinds
