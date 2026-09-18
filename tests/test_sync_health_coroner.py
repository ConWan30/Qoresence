"""Sync health + HID telemetry + SyncCoroner tests.

Deterministic slice:
- coalesced tremor/stick emits carry n/magnitude (bus sees ~10Hz not ~2kHz)
- sync-health state machine transitions with hysteresis
- SyncCoroner confidence gating applies only predeclared mitigations
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest

from qoresence.core import (
    ControllerConfig,
    EventType,
    RetinaEventBus,
    SessionAuthority,
    clock_ns,
)
from qoresence.lobes.controller import ControllerRuntime
from qoresence.observability.sync_coroner import (
    SyncCoroner,
    compose_verdict,
    local_coroner,
    make_coroner_from_config,
)
from qoresence.sync import hid_telemetry
from qoresence.sync.hid_report import pack_usb_report
from qoresence.sync.sync_health import (
    SHEDDING,
    SMOOTH,
    TIGHT,
    SyncHealth,
    reset_sync_health,
)


@pytest.fixture(autouse=True)
def _clean_slots():
    reset_sync_health()
    hid_telemetry.reset()
    yield
    reset_sync_health()
    hid_telemetry.reset()


def _report(**kw) -> bytes:
    return pack_usb_report(**kw)


def _runtime(bus: RetinaEventBus) -> ControllerRuntime:
    identity = SessionAuthority.mint(session_id="sync_test")
    return ControllerRuntime(
        config=ControllerConfig(enabled=True, poll_rate_hz=1000.0),
        bus=bus,
        session_head_ns=identity.session_head_ns,
    )


# ── HID telemetry slot ───────────────────────────────────────────────────


def test_telemetry_slot_newest_wins():
    hid_telemetry.publish_tremor(gyro=[1, 2, 3], accel=[4, 5, 6], clock_ns=100)
    hid_telemetry.publish_tremor(gyro=[7, 8, 9], accel=[10, 11, 12], clock_ns=200)
    hid_telemetry.publish_stick(stick="left", x=0.5, y=0.0, dx=0.1, dy=0.0, clock_ns=200)
    snap = hid_telemetry.snapshot()
    assert snap["tremor"]["gyro"] == [7, 8, 9]
    assert snap["tremor"]["clock_ns"] == 200
    assert snap["stick"]["left"]["x"] == 0.5
    assert snap["counts"]["tremor"] == 2
    assert snap["counts"]["stick"] == 1


def test_coalesced_tremor_emit_carries_n(tmp_path):
    bus = RetinaEventBus(
        session_id="t", jsonl_path=tmp_path / "e.jsonl", enable_ws=False
    )
    captured = []
    bus.subscribe(captured.append)
    rt = _runtime(bus)
    for _ in range(50):
        rt.ingest_report(_report(gyro=(10, 20, 30), accel=(100, 200, 300)))
    rt._flush_telemetry(clock_ns(), force=True)

    tremor = [e for e in captured if e.type == EventType.TREMOR_SAMPLE]
    # Coalescing guarantees: fewer events than samples, all samples accounted.
    assert 1 <= len(tremor) < 50
    assert sum(e.payload["n"] for e in tremor) == 50
    for e in tremor:
        assert e.payload["coalesced"] is True
        assert "causal_parent_ns" in e.payload
    assert tremor[-1].payload["gyro"] == [10, 20, 30]
    bus.close()


def test_coalesced_stick_emit_sums_magnitude(tmp_path):
    bus = RetinaEventBus(
        session_id="t", jsonl_path=tmp_path / "e.jsonl", enable_ws=False
    )
    captured = []
    bus.subscribe(captured.append)
    rt = _runtime(bus)
    for lx in (150, 170, 190):
        rt.ingest_report(_report(lx=lx))
    rt._flush_telemetry(clock_ns(), force=True)

    stick = [
        e
        for e in captured
        if e.type == EventType.STICK_MOTION and e.payload.get("stick") == "left"
    ]
    assert 1 <= len(stick) <= 3
    assert sum(e.payload["n"] for e in stick) == 3
    # (22 + 42 + 62) / 127 ≈ 0.9921 — magnitudes sum across the window.
    assert sum(e.payload["magnitude"] for e in stick) == pytest.approx(0.9921, abs=0.01)
    last = stick[-1].payload
    assert last["peak"] == pytest.approx((190 - 128) / 127.0, abs=0.001)
    assert last["x"] == (190 - 128) / 127.0
    bus.close()


def test_flush_rate_limited_by_sync_health(tmp_path):
    bus = RetinaEventBus(
        session_id="t", jsonl_path=tmp_path / "e.jsonl", enable_ws=False
    )
    captured = []
    bus.subscribe(captured.append)
    rt = _runtime(bus)
    rt.ingest_report(_report(gyro=(1, 1, 1), accel=(1, 1, 1)))
    rt._flush_telemetry(clock_ns(), force=True)
    rt.ingest_report(_report(gyro=(2, 2, 2), accel=(2, 2, 2)))
    rt._flush_telemetry(clock_ns())  # rate-limited: too soon after force
    tremor = [e for e in captured if e.type == EventType.TREMOR_SAMPLE]
    assert len(tremor) == 1
    bus.close()


# ── SyncHealth state machine ─────────────────────────────────────────────


def test_health_starts_smooth_and_stays():
    h = SyncHealth()
    assert h.level() == SMOOTH
    h.note_rates(fps_meas=60.0, fps_target=60.0, video_age_s=0.1)
    now = time.monotonic() + 10
    assert h.evaluate(now=now) == SMOOTH
    assert h.coalesce_hz() == 10.0


def test_health_degrades_to_tight_after_hold():
    h = SyncHealth()
    h.note_rates(fps_meas=60.0, fps_target=60.0, video_age_s=0.05)
    t0 = time.monotonic()
    h.note_rates(fps_meas=30.0, fps_target=60.0, video_age_s=0.6)
    # Warmup gate: degradation isn't trusted until ~2s of rates.
    assert h.evaluate(now=t0 + 0.5) == SMOOTH
    h.evaluate(now=t0 + 2.2)  # degraded condition first observed, hold starts
    assert h.evaluate(now=t0 + 3.4) == TIGHT  # held ≥ ~1s
    assert h.coalesce_hz() == 5.0


def test_health_sheds_then_recovers():
    h = SyncHealth()
    h.note_rates(fps_meas=60.0, fps_target=60.0)
    t0 = time.monotonic()
    h.note_rates(fps_meas=30.0, fps_target=60.0)
    h.evaluate(now=t0 + 2.2)
    assert h.evaluate(now=t0 + 3.4) == TIGHT
    h.note_rates(fps_meas=15.0, fps_target=60.0, video_age_s=1.5)
    h.evaluate(now=t0 + 4.0)  # critical first observed, hold starts
    assert h.evaluate(now=t0 + 6.2) == SHEDDING  # held ≥ ~2s
    assert h.coalesce_hz() == 2.0
    h.note_rates(fps_meas=58.0, fps_target=60.0, video_age_s=0.1)
    # note_rates self-evaluates, so the healthy hold started ~t0.
    assert h.evaluate(now=t0 + 7.0) == TIGHT  # healthy held ≥ ~5s
    assert h.evaluate(now=t0 + 12.2) == SMOOTH  # then ≥ ~3s more


def test_health_set_level_override_cools_down():
    h = SyncHealth()
    h.note_rates(fps_meas=60.0, fps_target=60.0, video_age_s=0.0)
    h.set_level(SHEDDING, reason="test", source="unit")
    assert h.level() == SHEDDING
    # During cooldown, auto-eval cannot override the external request.
    assert h.evaluate(now=time.monotonic() + 5) == SHEDDING
    # After cooldown the healthy-hold timer begins; steps take ~5s and ~3s.
    assert h.evaluate(now=time.monotonic() + 12) == SHEDDING
    assert h.evaluate(now=time.monotonic() + 18) == TIGHT
    assert h.evaluate(now=time.monotonic() + 21) == SMOOTH


# ── SyncCoroner ──────────────────────────────────────────────────────────


def test_compose_verdict_high_conf_applies_mapped_level():
    v = compose_verdict(
        bottleneck="hid_fanout_storm",
        bottleneck_confidence=0.8,
        severity=2.0,
        transient_noul=0.1,
        current_level=SMOOTH,
    )
    assert v["action"] == "apply"
    assert v["applied_level"] == SHEDDING


def test_compose_verdict_low_conf_only_observes():
    v = compose_verdict(
        bottleneck="hid_fanout_storm",
        bottleneck_confidence=0.2,
        severity=2.0,
        transient_noul=0.1,
        current_level=SMOOTH,
    )
    assert v["action"] != "apply"
    assert v["applied_level"] is None


def test_compose_verdict_mid_conf_soft_step_only():
    v = compose_verdict(
        bottleneck="capture_usb_contention",
        bottleneck_confidence=0.55,
        severity=2.0,
        transient_noul=0.2,
        current_level=SMOOTH,
    )
    assert v["action"] == "apply"
    assert v["applied_level"] == TIGHT  # soft gate caps at tight


def test_compose_verdict_transient_suppresses():
    v = compose_verdict(
        bottleneck="hid_fanout_storm",
        bottleneck_confidence=0.9,
        severity=2.5,
        transient_noul=0.8,
        current_level=SMOOTH,
    )
    assert v["action"] == "held_transient"
    assert v["applied_level"] is None


def test_compose_verdict_healthy_releases():
    v = compose_verdict(
        bottleneck="healthy",
        bottleneck_confidence=0.9,
        severity=0.2,
        transient_noul=0.5,
        current_level=SHEDDING,
    )
    assert v["action"] == "apply"
    assert v["applied_level"] == SMOOTH


def test_local_coroner_flags_fanout_storm():
    snap = {
        "sync": {"level": TIGHT, "fps_ratio": 0.5, "video_age_s": 0.4},
        "hid": {"emit_eps": 60.0, "reports_eps": 900.0},
    }
    out = local_coroner(snap)
    assert out["bottleneck"] == "hid_fanout_storm"


def test_local_coroner_ignores_raw_report_rate():
    """High poll rate alone is not a storm — only bus emit_eps is."""
    snap = {
        "sync": {"level": TIGHT, "fps_ratio": 0.3, "video_age_s": 0.4},
        "hid": {"emit_eps": 2.0, "reports_eps": 900.0},
    }
    out = local_coroner(snap)
    assert out["bottleneck"] == "capture_usb_contention"


def test_local_coroner_healthy_when_nominal():
    snap = {
        "sync": {"level": SMOOTH, "fps_ratio": 0.98, "video_age_s": 0.05},
        "hid": {"emit_eps": 10.0, "reports_eps": 300.0},
    }
    out = local_coroner(snap)
    assert out["bottleneck"] == "healthy"


def test_coroner_disabled_by_default():
    cfg = SimpleNamespace(enabled=False)
    assert make_coroner_from_config(cfg) is None


def test_coroner_tick_applies_mitigation(tmp_path):
    health = SyncHealth()
    health.set_level(SMOOTH, reason="seed", source="test")
    health._override = None  # clear seed override so apply can move it
    health._level = TIGHT  # simulate degraded deterministic state

    def _ask(_snap):
        return {
            "bottleneck": "hid_fanout_storm",
            "bottleneck_confidence": 0.9,
            "severity": 2.5,
            "transient_noul": 0.1,
            "source": "test",
        }

    cfg = SimpleNamespace(enabled=True, cadence_s=0.05, out_dir=str(tmp_path))
    cor = SyncCoroner(cfg, sync_health=health, ask_fn=_ask)
    try:
        time.sleep(0.25)
    finally:
        cor.stop()
    assert health.level() == SHEDDING
    st = cor.stats()
    assert st["ticks"] >= 1
    assert st["applied"] >= 1
    rows = (tmp_path / "sync_coroner.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert rows, "expected JSONL verdict rows"
    assert json.loads(rows[-1])["bottleneck"] == "hid_fanout_storm"


def test_coroner_never_emits_bus_events(tmp_path):
    """Observation-plane guarantee: coroner may not emit on the bus."""
    health = SyncHealth()
    bus = RetinaEventBus(
        session_id="t", jsonl_path=tmp_path / "e.jsonl", enable_ws=False
    )
    captured = []
    bus.subscribe(captured.append)
    cfg = SimpleNamespace(enabled=True, cadence_s=0.05, out_dir=str(tmp_path))
    cor = SyncCoroner(cfg, sync_health=health, bus=bus, ask_fn=lambda s: None)
    try:
        time.sleep(0.2)
    finally:
        cor.stop()
        bus.close()
    assert captured == []
