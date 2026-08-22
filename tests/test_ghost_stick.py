"""Ghost Stick — delay onto LIVE seq, vanish on idle / Same-Seq / coupling."""

from __future__ import annotations

from qoresence.sync.ghost_stick import (
    decide_ghost_stick,
    ghost_stick_enabled,
    set_ghost_stick_enabled,
)
from qoresence.sync.input_ring import AnalogPose, InputRing


def _ok(**kw):
    pose = kw.pop("pose", AnalogPose(clock_ns=1, lx=0.4, ly=-0.2, r2=0.8, l2=0.0))
    base = {
        "enabled": True,
        "paint_reason": "ok",
        "same_seq": True,
        "plane_dim": False,
        "live_seq": 10,
        "widget_seq": 10,
        "coupling": 0.4,
        "lag_ms": 48.0,
    }
    base.update(kw)
    return decide_ghost_stick(pose=pose, **base)


def test_default_on_unless_explicit_off(monkeypatch):
    monkeypatch.delenv("QORESENCE_GHOST_STICK", raising=False)
    set_ghost_stick_enabled(False)
    assert ghost_stick_enabled() is True
    monkeypatch.setenv("QORESENCE_GHOST_STICK", "0")
    assert ghost_stick_enabled() is False
    d_off = decide_ghost_stick(
        enabled=False,
        paint_reason="ok",
        same_seq=True,
        plane_dim=False,
        live_seq=10,
        widget_seq=10,
        coupling=0.4,
        pose=AnalogPose(clock_ns=1, lx=0.4, ly=0.0, r2=0.8, l2=0.0),
        lag_ms=48.0,
    )
    assert d_off.paint is False
    assert d_off.reason == "off"


def test_paints_when_same_seq_and_coupled():
    d = _ok()
    assert d.paint is True
    assert d.reason == "ok"
    assert d.lx == 0.4
    assert d.r2 == 0.8
    assert d.lag_ms == 48.0
    assert d.frame_seq == 10


def test_seq_skew_ghost_from_n_cannot_sit_on_n_plus_k():
    d = _ok(same_seq=False, live_seq=20, widget_seq=7)
    assert d.paint is False
    assert d.reason == "seq_skew"
    assert d.lx == 0.0
    skew = _ok(paint_reason="seq_skew")
    assert skew.paint is False
    assert skew.reason == "seq_skew"


def test_vanish_idle_and_no_interpolate():
    idle = _ok(pose=AnalogPose(clock_ns=1, lx=0.0, ly=0.0, r2=0.0, l2=0.0))
    assert idle.paint is False
    assert idle.reason == "idle"
    missing = _ok(pose=None)
    assert missing.paint is False
    assert missing.reason == "idle"


def test_vanish_not_play_and_coupling():
    menu = _ok(plane_dim=True, paint_reason="not_play")
    assert menu.paint is False
    assert menu.reason == "not_play"
    low = _ok(coupling=0.02)
    assert low.paint is False
    assert low.reason == "coupling"


def test_pose_at_delays_and_does_not_interpolate_silence():
    ring = InputRing()
    t0 = 1_000_000_000
    ring.set_hold(clock_ns=t0, r2=0.9, left=0.5, lx=0.6, ly=-0.3)
    lag_ns = int(48 * 1e6)
    got = ring.pose_at(t0 + lag_ns, max_age_ms=80)
    assert got is not None
    assert got.lx == 0.6
    assert got.r2 == 0.9
    stale = ring.pose_at(t0 + int(200 * 1e6), max_age_ms=80)
    assert stale is None
