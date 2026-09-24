"""TypeSafe Noul observatory — observation plane, fail-closed."""

from __future__ import annotations

import threading
import time

from qoresence.core.unified_config import NoulConfig, RetinaUnifiedConfig
from qoresence.observability.noul_observatory import (
    NoulObservatory,
    compose_honesty_lattice,
    compose_observatory,
    local_heuristic_nouls,
    make_noul_from_config,
)


def test_noul_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.noul.enabled is False
    assert make_noul_from_config(config.noul) is None


def test_compose_never_licenses_digits():
    out = compose_observatory(
        parsed={"home_score": 14, "away_score": 7, "left_team": "NYJ", "right_team": "TEN"},
        grounded_noul=0.95,
        true_pause_noul=0.05,
        clip_noul=0.9,
        hud_kind="live_hud",
        hud_confidence=0.9,
        coupling=0.8,
        red_zone=True,
    )
    assert out["licenses_digits"] is False
    assert out["may_consider_clip"] is True
    assert out["board_speech"] == "confirm_ticket"
    assert out["licenses_digits"] is False


def test_honesty_lattice_ident_on_last_good_temptation():
    lat = compose_honesty_lattice(
        board_honesty=0.0,
        presence_density=0.0,
        last_good_temptation=0.88,
        grounded_noul=0.12,
    )
    assert lat["honesty_band"] == "ident"
    assert lat["ident_now"] is True
    assert lat["presence_token"] == "idle"


def test_select_plate_lattice_ident():
    parsed = {
        "home_score": 20,
        "away_score": 0,
        "paused": True,
        "left_team": None,
        "right_team": None,
    }
    h = local_heuristic_nouls({"parsed": parsed})
    out = compose_observatory(
        parsed=parsed,
        grounded_noul=h["grounded_noul"],
        true_pause_noul=h["true_pause_noul"],
        hud_kind=h["hud_kind"],
        hud_confidence=h["hud_confidence"],
        board_honesty=h["board_honesty"],
        presence_density=h["presence_density"],
        last_good_temptation=h["last_good_temptation"],
    )
    assert out["honesty_band"] == "ident"
    assert out["licenses_digits"] is False


def test_compose_fail_closed_on_coin_flip_noul():
    out = compose_observatory(
        parsed={"home_score": 12, "away_score": 15},
        grounded_noul=0.51,
        hud_kind="live_hud",
        hud_confidence=0.4,
    )
    assert out["licenses_digits"] is False
    assert out["may_consider_clip"] is False
    assert out["hud_kind"] is None


def test_select_plate_ungrounded():
    parsed = {
        "home_score": 20,
        "away_score": 0,
        "paused": True,
        "left_team": None,
        "right_team": None,
    }
    h = local_heuristic_nouls({"parsed": parsed})
    out = compose_observatory(
        parsed=parsed,
        grounded_noul=h["grounded_noul"],
        true_pause_noul=h["true_pause_noul"],
        hud_kind=h["hud_kind"],
        hud_confidence=h["hud_confidence"],
    )
    assert h["hud_kind"] == "select_plate"
    assert out["board_speech"] == "vlm_ungrounded"
    assert out["licenses_digits"] is False


def test_preplay_not_true_pause():
    parsed = {
        "home_score": 13,
        "away_score": 31,
        "paused": True,
        "left_team": "NYJ",
        "right_team": "TEN",
        "visible_control": {"prompt": "Preplay"},
    }
    h = local_heuristic_nouls({"parsed": parsed})
    out = compose_observatory(
        parsed=parsed,
        grounded_noul=h["grounded_noul"],
        true_pause_noul=h["true_pause_noul"],
        hud_kind=h["hud_kind"],
        hud_confidence=h["hud_confidence"],
    )
    assert h["hud_kind"] == "preplay"
    assert h["true_pause_noul"] < 0.3
    assert out["board_speech"] == "confirm_ticket"
    assert out["licenses_digits"] is False


class _DummyBus:
    def __init__(self) -> None:
        self._cb = None

    def subscribe_raw(self, cb):
        self._cb = cb

        def _unsub():
            self._cb = None

        return _unsub

    def emit(self, rec):
        if self._cb:
            self._cb(rec)


class _Evt:
    def __init__(self, payload):
        self.type = "visual"
        self.payload = payload
        self.clock_ns = 1
        self.source_lobe = "visual"


def test_hot_path_only_enqueues(tmp_path):
    judged = []
    barrier = threading.Event()

    def ask(rec):
        barrier.wait(timeout=2.0)
        judged.append(rec)
        return local_heuristic_nouls(rec)

    bus = _DummyBus()
    obs = NoulObservatory(
        NoulConfig(enabled=True, out_dir=str(tmp_path), queue_size=8),
        bus=bus,
        ask_fn=ask,
    )
    t0 = time.perf_counter()
    bus.emit(
        _Evt(
            {
                "parsed": {
                    "home_score": 7,
                    "away_score": 0,
                    "left_team": "KC",
                    "right_team": "BUF",
                },
                "coupling": 0.2,
            }
        )
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    assert elapsed_ms < 50
    assert judged == []
    barrier.set()
    deadline = time.time() + 2
    while obs.stats()["judged"] < 1 and time.time() < deadline:
        time.sleep(0.02)
    assert obs.stats()["judged"] >= 1
    assert obs.stats()["licenses_digits"] is False
    obs.stop()


def _kind_answers(kind):
    return {"hud_kind": kind, "hud_confidence": 0.9, "presence_density": 0.0}


def test_run_ring_appends_only_on_change(tmp_path):
    answers = {"a": _kind_answers("live_hud")}
    obs = NoulObservatory(
        NoulConfig(enabled=True, out_dir=str(tmp_path), queue_size=8),
        ask_fn=lambda rec: answers["a"],
    )
    try:
        parsed = {"home_score": 7, "away_score": 0}
        for ns in (100, 200, 300):
            obs._judge({"clock_ns": ns, "parsed": parsed})
        answers["a"] = _kind_answers("menu")
        obs._judge({"clock_ns": 400, "parsed": parsed})
        obs._judge({"clock_ns": 500, "parsed": parsed})
        answers["a"] = _kind_answers("not_a_kind")
        obs._judge({"clock_ns": 600, "parsed": parsed})
        runs = list(obs._runs)
        assert [r[0] for r in runs] == [100, 400, 600]
        assert [r[1] for r in runs] == ["live_hud", "menu", "unknown"]
        assert all(r[2] == "idle" for r in runs)
    finally:
        obs.stop()


def test_run_ring_bounded_and_window_includes_prior_run(tmp_path):
    from qoresence.observability.noul_observatory import RUN_RING_MAX

    obs = NoulObservatory(NoulConfig(enabled=True, out_dir=str(tmp_path), queue_size=8))
    try:
        kinds = ("live_hud", "menu")
        for i in range(RUN_RING_MAX + 50):
            obs._runs.append((i * 10, kinds[i % 2], "idle"))
        assert len(obs._runs) == RUN_RING_MAX
        obs._runs.clear()
        obs._runs.extend([(100, "menu", "idle"), (500, "live_hud", "join"), (900, "loading", "idle")])
        win = obs.runs_in_window(300, 800)
        assert win == [(100, "menu", "idle"), (500, "live_hud", "join")]
        assert obs.runs_in_window(950, 1000) == [(900, "loading", "idle")]
    finally:
        obs.stop()
