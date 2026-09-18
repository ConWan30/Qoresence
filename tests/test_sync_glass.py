"""SyncGlass v0 — observation plane, fail-closed.

Locks in: enqueue-only hot path, never emits bus events, never consults
lag_estimator / ticket book / capture on the event path, never licenses
digits, never applies lag_center recenter or capture fps, fallback
dark/observe, --play / default OFF.
"""

from __future__ import annotations

import json
import time
from dataclasses import fields
from pathlib import Path

from qoresence.core.unified_config import (
    RetinaUnifiedConfig,
    SyncGlassConfig,
)
from qoresence.observability.sync_glass import (
    SyncGlassSentinel,
    compose_sync_verdict,
    local_sync_answers,
    make_sync_glass_from_config,
)
from qoresence.observability.sync_glass_questions import (
    ACTIONS,
    CONF_RECENTER,
    GLYPHS,
    LAG_CLASSES,
    sync_glass_questions,
)


def _sentinel(tmp_path, **kw):
    cfg = SyncGlassConfig(enabled=True, out_dir=str(tmp_path), cadence_s=0.05)
    return SyncGlassSentinel(cfg, **kw)


def _healthy_state(**extra):
    state = {
        "clock_ns": 1,
        "frame_seq": 1,
        "video": {"age_s": 0.04, "frames": 120, "pll_lock": True},
        "hid": {
            "source": "usb_play",
            "edges_last_n": ["r2"],
            "apm": 40.0,
            "stick_heat": 0.4,
            "hid_at_ns": 1,
            "sync_lag_ms": 48.0,
            "lag_center_ms": 50.0,
        },
        "haptic": {"co_occur_recent": False, "probe_ok": True},
        "capture": {"starve": False, "dshow_name": "USB3.0 Video"},
        "ticket_glass": {"lock": "unknown", "enabled": False},
    }
    state.update(extra)
    return state


class _DummyBus:
    def __init__(self) -> None:
        self._cb = None
        self.emitted = []
        self.emitted_raw = []

    def subscribe_raw(self, cb):
        self._cb = cb

        def _unsub():
            self._cb = None

        return _unsub

    def emit(self, rec):
        self.emitted.append(rec)
        if self._cb:
            self._cb(rec)

    def emit_raw(self, rec):
        self.emitted_raw.append(rec)
        if self._cb:
            self._cb(rec)


class _Evt:
    def __init__(self, payload, typ="visual"):
        self.type = typ
        self.payload = payload
        self.clock_ns = 1
        self.source_lobe = "visual"


def test_default_off():
    assert SyncGlassConfig().enabled is False
    assert make_sync_glass_from_config(SyncGlassConfig()) is None
    names = {f.name for f in fields(RetinaUnifiedConfig)}
    assert "sync_glass" in names


def test_play_alone_does_not_enable():
    """--play must not flip SyncGlass on (flag/env remain opt-in)."""
    text = Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "--sync-glass" in text
    assert "QORESENCE_SYNC_GLASS=1" in text
    play_idx = text.find('if getattr(args, "play", False):')
    assert play_idx > 0
    play_block = text[play_idx : play_idx + 12000]
    assert "sync_glass" not in play_block


def test_compose_never_licenses_digits():
    for action in ACTIONS:
        out = compose_sync_verdict(
            bind_healthy=0.95,
            lag_class="ok",
            lag_confidence=0.95,
            haptic_coupled=0.1,
            action=action,
            action_confidence=0.95,
            severity=2,
            severity_confidence=0.95,
        )
        assert out["licenses_digits"] is False
        assert out["recenter_applied"] is False
        assert out["capture_fps_changed"] is False
        assert out["haptic_authored"] is False
        assert "digits" not in out


def test_gates_observe_soft_act():
    observe = compose_sync_verdict(
        bind_healthy=0.8,
        lag_class="picture_ahead",
        lag_confidence=0.2,
        haptic_coupled=0.2,
        action="flag_operator",
        action_confidence=0.2,
        severity=3,
        severity_confidence=0.2,
    )
    assert observe["bands"]["lag_class"] == "observe"
    assert observe["lag_class"] == "unknown"
    assert observe["action"] == "observe"
    assert observe["glyphs"]["lag"] == "unknown"
    assert observe["glyphs"]["haptic"] == "off"
    assert observe["severity"] == 0

    soft = compose_sync_verdict(
        bind_healthy=0.55,
        lag_class="picture_ahead",
        lag_confidence=0.55,
        haptic_coupled=0.5,
        action="flag_operator",
        action_confidence=0.55,
        severity=2,
        severity_confidence=0.55,
    )
    assert soft["bands"]["lag_class"] == "soft"
    assert soft["lag_class"] == "picture_ahead"
    assert soft["action"] == "observe"  # glyphs only; no act
    assert soft["glyphs"]["bind"] == "soft"
    assert soft["glyphs"]["haptic"] == "unknown"
    assert soft["severity"] == 2

    act = compose_sync_verdict(
        bind_healthy=0.85,
        lag_class="ok",
        lag_confidence=0.8,
        haptic_coupled=0.85,
        action="observe",
        action_confidence=0.8,
        severity=0,
        severity_confidence=0.8,
    )
    assert act["bands"]["lag_class"] == "act"
    assert act["lag_class"] == "ok"
    assert act["glyphs"]["bind"] == "ok"
    assert act["glyphs"]["haptic"] == "on"
    assert act["licenses_digits"] is False


def test_recenter_soft_is_advisory_never_applied():
    low = compose_sync_verdict(
        bind_healthy=0.4,
        lag_class="picture_ahead",
        lag_confidence=0.9,
        action="recenter_soft",
        action_confidence=0.8,
        severity=2,
        severity_confidence=0.9,
    )
    assert 0.8 < CONF_RECENTER
    assert low["action"] == "observe"
    assert low["action_raw"] == "recenter_soft"
    assert low["recenter_applied"] is False
    assert low["capture_fps_changed"] is False

    high = compose_sync_verdict(
        bind_healthy=0.4,
        lag_class="picture_ahead",
        lag_confidence=0.95,
        action="recenter_soft",
        action_confidence=0.9,
        severity=2,
        severity_confidence=0.95,
    )
    assert high["action"] == "recenter_soft"
    assert high["recenter_applied"] is False
    assert high["capture_fps_changed"] is False
    assert high["licenses_digits"] is False


def test_fallback_dark_observe():
    answers = local_sync_answers({})
    assert answers["action"] == "dark_overlay"
    assert answers["lag_class"] == "unknown"
    out = compose_sync_verdict(
        bind_healthy=answers["bind_healthy"],
        lag_class=answers["lag_class"],
        lag_confidence=answers["lag_confidence"],
        haptic_coupled=answers["haptic_coupled"],
        action=answers["action"],
        action_confidence=answers["action_confidence"],
        severity=answers["severity"],
        severity_confidence=answers["severity_confidence"],
    )
    assert out["action"] in {"dark_overlay", "observe"}
    assert out["glyphs"]["bind"] in {"soft", "unknown"}
    assert out["glyphs"]["lag"] == "unknown"
    assert out["licenses_digits"] is False
    assert out["recenter_applied"] is False
    assert out["capture_fps_changed"] is False


def test_fallback_hid_empty_usb_is_path_b_observe():
    """Laptop USB empty is honest Path B — observe, never a fps retune."""
    answers = local_sync_answers(
        {
            "video": {"age_s": 0.05, "frames": 80, "pll_lock": False},
            "hid": {
                "source": "empty",
                "edges_last_n": [],
                "sync_lag_ms": None,
                "lag_center_ms": None,
            },
            "haptic": {"co_occur_recent": False, "probe_ok": None},
            "capture": {"starve": False},
        }
    )
    assert answers["lag_class"] == "hid_empty_usb"
    assert answers["action"] == "observe"
    out = compose_sync_verdict(
        bind_healthy=answers["bind_healthy"],
        lag_class=answers["lag_class"],
        lag_confidence=answers["lag_confidence"],
        haptic_coupled=answers["haptic_coupled"],
        action=answers["action"],
        action_confidence=answers["action_confidence"],
        severity=answers["severity"],
        severity_confidence=answers["severity_confidence"],
    )
    assert out["lag_class"] == "hid_empty_usb"
    assert out["action"] == "observe"
    assert out["glyphs"]["lag"] == "hid_empty_usb"
    assert out["recenter_applied"] is False
    assert out["capture_fps_changed"] is False


def test_fallback_capture_starve_flags_operator_without_retune():
    answers = local_sync_answers(
        {
            "video": {"age_s": 2.4, "frames": 10, "pll_lock": False},
            "hid": {"source": "usb_play", "edges_last_n": ["x"], "sync_lag_ms": 48.0},
            "capture": {"starve": True},
            "haptic": {"co_occur_recent": False, "probe_ok": True},
        }
    )
    assert answers["lag_class"] == "capture_starve"
    assert answers["action"] == "flag_operator"
    out = compose_sync_verdict(
        bind_healthy=answers["bind_healthy"],
        lag_class=answers["lag_class"],
        lag_confidence=answers["lag_confidence"],
        haptic_coupled=answers["haptic_coupled"],
        action=answers["action"],
        action_confidence=answers["action_confidence"],
        severity=answers["severity"],
        severity_confidence=answers["severity_confidence"],
    )
    assert out["action"] == "flag_operator"
    assert out["glyphs"]["lag"] == "capture_starve"
    assert out["severity"] == 3
    assert out["recenter_applied"] is False
    assert out["capture_fps_changed"] is False


def test_fallback_in_band_ok():
    answers = local_sync_answers(_healthy_state())
    assert answers["lag_class"] == "ok"
    assert answers["action"] == "observe"
    assert answers["bind_healthy"] >= 0.7
    out = compose_sync_verdict(
        bind_healthy=answers["bind_healthy"],
        lag_class=answers["lag_class"],
        lag_confidence=answers["lag_confidence"],
        haptic_coupled=answers["haptic_coupled"],
        action=answers["action"],
        action_confidence=answers["action_confidence"],
        severity=answers["severity"],
        severity_confidence=answers["severity_confidence"],
    )
    assert out["lag_class"] == "ok"
    assert out["glyphs"]["bind"] == "ok"
    assert out["licenses_digits"] is False


def test_sanitize_drops_pixels_and_truth_plane():
    from qoresence.observability.sync_glass import _sanitize

    raw = {
        "video": {"age_s": 0.1, "pll_lock": True},
        "jpeg": "not-a-frame",
        "frame": b"xxx",
        "qortroller": {"wrap": True},
        "truth": {"claim": True},
        "hid": {"source": "usb_play", "crop_jpeg": "abc"},
    }
    clean = _sanitize(raw)
    assert "jpeg" not in clean
    assert "frame" not in clean
    assert "qortroller" not in clean
    assert "truth" not in clean
    assert "crop_jpeg" not in clean["hid"]
    assert clean["video"]["pll_lock"] is True


def test_hot_path_only_enqueues_and_never_blocks(tmp_path):
    """_on_event must not consult clocks, PLL, or capture (grab waits for nobody)."""

    def _boom(_state=None):
        raise AssertionError("lobe / clock accessor touched on event path")

    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        state_fn=_boom,
        ask_fn=_boom,
    )
    try:
        t0 = time.perf_counter()
        for _ in range(64):
            bus.emit(_Evt({"age_s": 0.04, "frame_seq": 12, "sync_lag_ms": 48}))
        assert time.perf_counter() - t0 < 1.0
        assert sen._queue.qsize() > 0
        src = Path("qoresence/observability/sync_glass.py").read_text(encoding="utf-8")
        on_event = src.split("def _on_event", 1)[1].split("def _drain_live", 1)[0]
        assert "get_ticket_book" not in on_event
        assert "get_lag_estimator" not in on_event
        assert "get_latest_stamp" not in on_event
        assert "get_sync_health" not in on_event
        assert "observe_phase" not in on_event
        assert "set_level" not in on_event
        assert "VideoCapture" not in on_event
    finally:
        sen.stop()


def test_worker_never_emits_bus_events(tmp_path):
    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        state_fn=lambda: _healthy_state(),
        ask_fn=lambda s: local_sync_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        stats = sen.stats()
        assert stats["judged"] >= 1
        assert stats["licenses_digits"] is False
        assert stats["recenter_applied"] is False
        assert stats["capture_fps_changed"] is False
        assert stats["haptic_authored"] is False
        assert bus.emitted_raw == []
        last = sen.last()
        assert last.get("plane") == "qoresence-observation"
        assert set(last.get("glyphs", {})) == {"bind", "lag", "haptic"}
    finally:
        sen.stop()


def test_jsonl_audit_written(tmp_path):
    sen = _sentinel(
        tmp_path,
        state_fn=lambda: _healthy_state(),
        ask_fn=lambda s: local_sync_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        sen.stop()
        path = tmp_path / "sync_glass.jsonl"
        assert path.exists()
        row = json.loads(path.read_text().strip().splitlines()[0])
        assert row["licenses_digits"] is False
        assert row["recenter_applied"] is False
        assert row["capture_fps_changed"] is False
        assert set(row["glyphs"]) == {"bind", "lag", "haptic"}
    finally:
        sen.stop()


def test_disabled_by_default_flag_only(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_SYNC_GLASS", raising=False)
    sen = SyncGlassSentinel(SyncGlassConfig(enabled=False, out_dir=str(tmp_path)))
    assert sen.enabled is False
    sen._on_event(_Evt({"age_s": 0.1, "frame_seq": 1}))
    assert sen._queue.qsize() == 0
    sen.stop()


def test_env_enables(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.setenv("QORESENCE_SYNC_GLASS", "1")
    sen = SyncGlassSentinel(SyncGlassConfig(enabled=False, out_dir=str(tmp_path), cadence_s=0.05))
    try:
        assert sen.enabled is True
    finally:
        sen.stop()


def test_jev_umbrella_enables_make(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_SYNC_GLASS", raising=False)
    cfg = SyncGlassConfig(enabled=False, out_dir=str(tmp_path), cadence_s=0.05)
    sen = make_sync_glass_from_config(cfg, jev_enabled=True)
    try:
        assert sen is not None
        assert sen.enabled is True
    finally:
        if sen is not None:
            sen.stop()


def test_source_never_emits_or_retunes():
    src = Path("qoresence/observability/sync_glass.py").read_text(encoding="utf-8")
    assert "emit_raw" not in src
    assert "bus.emit" not in src
    assert "set_level" not in src
    assert "observe_phase" not in src
    assert ".observe(" not in src
    assert "VideoCapture" not in src
    assert "streamer-fps" not in src
    qsrc = Path("qoresence/observability/sync_glass_questions.py").read_text(encoding="utf-8")
    assert "digits_ok" not in qsrc
    assert "licenses_digits" in qsrc
    assert "qortroller" in qsrc.lower() or "Truth-plane" in qsrc
    assert "author rumble" in qsrc.lower()


def test_questions_ids_when_sdk_present():
    qs = sync_glass_questions()
    if not qs:
        return
    assert set(qs) == {
        "bind_healthy",
        "lag_class",
        "haptic_coupled",
        "action",
        "severity",
    }


def test_health_stats_shape(tmp_path):
    sen = _sentinel(
        tmp_path,
        state_fn=lambda: _healthy_state(),
        ask_fn=lambda s: local_sync_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        stats = sen.stats()
        assert stats["enabled"] is True
        assert stats["licenses_digits"] is False
        assert stats["recenter_applied"] is False
        assert stats["capture_fps_changed"] is False
        assert stats["haptic_authored"] is False
        assert "bind" in stats["glyphs"]
        assert "lag" in stats["glyphs"]
        assert "haptic" in stats["glyphs"]
    finally:
        sen.stop()


def test_closed_option_sets():
    assert "unknown" in LAG_CLASSES
    assert "hid_empty_usb" in LAG_CLASSES
    assert "capture_starve" in LAG_CLASSES
    assert "observe" in ACTIONS
    assert "recenter_soft" in ACTIONS
    assert "dark_overlay" in ACTIONS
    assert GLYPHS == ("bind", "lag", "haptic")


def test_health_wired_in_deck():
    text = Path("qoresence/deck/server.py").read_text(encoding="utf-8")
    assert "get_sync_glass" in text
    assert 'health["sync_glass"]' in text
    assert 'body["sync_glass"]' in text
