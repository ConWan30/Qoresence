"""CIVIF v0 coupling sidecar — observation plane only."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from qoresence.core.coupled_event import (
    CIVIF_SCHEMA,
    build_coupling_sidecar,
    validate_coupling,
)


def _sidecar(**kw):
    defaults = dict(
        clip_id="hdmi_clip_test",
        session_id="sess-1",
        start_ns=1_000,
        end_ns=2_000,
        frame_start=1,
        frame_end=10,
        video_path="clips/hdmi_clip_test.mp4",
        events=[],
        coupling={},
        coupling_history=[],
    )
    defaults.update(kw)
    return build_coupling_sidecar(**defaults)


def test_empty_pad_is_valid():
    data = _sidecar()
    assert data["schema_version"] == CIVIF_SCHEMA
    assert data["input"]["bodied"] is False
    assert data["input"]["reason"] == "pad_not_on_this_host"
    assert data["input"]["events"] == []
    assert data["situation"]["home_score"] is None
    assert validate_coupling(data) == []


def test_legacy_keys_preserved():
    data = _sidecar(coupling={"coupling": 0.4, "pll_lock": True})
    assert "clip.clock_ns.start" in data
    assert "coupling" in data
    assert data["coupling"]["coupling"] == 0.4
    assert "coupling_history" in data
    assert "input_ring_events" in data


def test_monotonic_clocks_fail():
    data = _sidecar(
        events=[
            {"clock_ns": 1500},
            {"clock_ns": 1200},
        ],
    )
    errs = validate_coupling(data)
    assert any("monotonic" in e for e in errs)


def test_event_outside_window_fails():
    data = _sidecar(events=[{"clock_ns": 50}])
    errs = validate_coupling(data)
    assert any("before clip window" in e for e in errs)


def test_scores_without_lock_fail():
    data = _sidecar()
    data["situation"]["home_score"] = 21
    data["situation"]["away_score"] = 14
    data["situation"]["board_locked"] = False
    errs = validate_coupling(data)
    assert any("board_locked" in e for e in errs)


def test_locked_scores_ok():
    data = _sidecar(situation={"board_locked": True, "home_score": 21, "away_score": 14})
    assert data["situation"]["home_score"] == 21
    assert validate_coupling(data) == []


def test_legacy_sidecar_without_schema_ok():
    assert validate_coupling({"clip.clock_ns.start": 1, "clip.clock_ns.end": 2, "coupling": {}}) == []


def test_validate_cli(tmp_path):
    good = tmp_path / "ok.coupling.json"
    good.write_text(json.dumps(_sidecar()), encoding="utf-8")
    bad = tmp_path / "bad.coupling.json"
    payload = _sidecar()
    payload["situation"]["home_score"] = 7
    payload["situation"]["board_locked"] = False
    bad.write_text(json.dumps(payload), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "validate_coupling.py"
    r_ok = subprocess.run([sys.executable, str(script), str(good)], check=False)
    r_bad = subprocess.run([sys.executable, str(script), str(bad)], check=False)
    assert r_ok.returncode == 0
    assert r_bad.returncode == 1
