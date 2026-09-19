"""Mint verifier — observation plane, fail-closed.

Locks in: compose never licenses digits, empty ticks do not remint,
enqueue-only hot path, deterministic refuse cannot be talked down.
"""

from __future__ import annotations

import time

from qoresence.core.unified_config import MintVerifierConfig, RetinaUnifiedConfig
from qoresence.observability.mint_verifier import (
    MintVerifierSentinel,
    compose_mint_verdict,
    local_mint_answers,
    make_mint_verifier_from_config,
)


def _sentinel(tmp_path, **kw):
    cfg = MintVerifierConfig(enabled=True, out_dir=str(tmp_path), cadence_s=0.05)
    return MintVerifierSentinel(cfg, **kw)


def _compose_from_state(state: dict) -> dict:
    answers = local_mint_answers(state)
    return compose_mint_verdict(
        same_game=answers.get("same_game"),
        scorebug_in_crop=answers.get("scorebug_in_crop"),
        pair_matches_ticket=answers.get("pair_matches_ticket"),
        legal_transition=answers.get("legal_transition"),
        hud_kind=answers.get("hud_kind"),
        hud_confidence=answers.get("hud_confidence"),
        has_ticket=bool((state.get("ticket") or {}).get("has_ticket", True)),
        gate_reason=state.get("gate_reason"),
        pair_differs=answers.get("pair_differs"),
    )


def test_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.mint_verifier.enabled is False
    assert make_mint_verifier_from_config(config.mint_verifier) is None


def test_umbrella_jev_enables():
    sen = make_mint_verifier_from_config(
        MintVerifierConfig(enabled=False),
        jev_enabled=True,
    )
    assert sen is not None
    assert sen.enabled is True
    sen.stop()


def test_compose_never_licenses_digits():
    for action in ("hold", "remint", "blank", "observe"):
        out = compose_mint_verdict(
            same_game=0.9,
            scorebug_in_crop=0.9 if action != "observe" else 0.1,
            pair_matches_ticket=0.9 if action == "hold" else 0.1,
            legal_transition=0.9 if action == "remint" else 0.1,
            hud_kind="live_hud" if action != "blank" else "menu",
            hud_confidence=0.85,
            has_ticket=True,
            pair_differs=action == "remint",
        )
        assert out["licenses_digits"] is False
        assert out["plane"] == "qoresence-observation"
        assert "digits" not in out


def test_empty_tick_observe_not_remint():
    out = _compose_from_state(
        {
            "ticket": {
                "has_ticket": True,
                "home_score": 21,
                "away_score": 7,
                "home_team": "LOU",
                "away_team": "ND",
            },
            "live": {
                "home_score": None,
                "away_score": None,
                "hud_kind": "no_board",
                "vlm_status": "stale",
                "last_reason": "tick",
            },
        }
    )
    assert out["action"] == "observe"
    assert out["licenses_digits"] is False


def test_legal_score_change_remint():
    out = _compose_from_state(
        {
            "ticket": {
                "has_ticket": True,
                "home_score": 21,
                "away_score": 7,
                "home_team": "LOU",
                "away_team": "ND",
            },
            "live": {
                "home_score": 21,
                "away_score": 14,
                "home_team": "LOU",
                "away_team": "ND",
                "hud_kind": "live_hud",
            },
        }
    )
    assert out["action"] == "remint"
    assert out["licenses_digits"] is False


def test_matching_live_board_hold():
    out = _compose_from_state(
        {
            "ticket": {
                "has_ticket": True,
                "home_score": 21,
                "away_score": 7,
                "home_team": "LOU",
                "away_team": "ND",
            },
            "live": {
                "home_score": 21,
                "away_score": 7,
                "home_team": "LOU",
                "away_team": "ND",
                "hud_kind": "live_hud",
            },
        }
    )
    assert out["action"] == "hold"


def test_ocr_echo_not_remint():
    out = _compose_from_state(
        {
            "ticket": {
                "has_ticket": True,
                "home_score": 7,
                "away_score": 0,
                "home_team": "LOU",
                "away_team": "ND",
            },
            "live": {
                "home_score": 20,
                "away_score": 20,
                "home_team": "LOU",
                "away_team": "ND",
                "hud_kind": "live_hud",
            },
        }
    )
    assert out["action"] != "remint"
    assert out["licenses_digits"] is False


def test_identity_swap_blank():
    out = _compose_from_state(
        {
            "ticket": {
                "has_ticket": True,
                "home_score": 21,
                "away_score": 7,
                "home_team": "LOU",
                "away_team": "ND",
            },
            "live": {
                "home_score": 14,
                "away_score": 3,
                "home_team": "ALA",
                "away_team": "UGA",
                "hud_kind": "live_hud",
            },
        }
    )
    assert out["action"] == "blank"


def test_menu_blank():
    out = _compose_from_state(
        {
            "ticket": {
                "has_ticket": True,
                "home_score": 21,
                "away_score": 7,
            },
            "live": {
                "home_score": None,
                "away_score": None,
                "hud_kind": "menu",
            },
        }
    )
    assert out["action"] == "blank"


def test_no_ticket_observe():
    out = compose_mint_verdict(
        same_game=0.9,
        scorebug_in_crop=0.9,
        pair_matches_ticket=0.9,
        has_ticket=False,
        hud_kind="live_hud",
        hud_confidence=0.9,
    )
    assert out["action"] == "observe"


def test_deterministic_refuse_cannot_be_talked_down():
    out = compose_mint_verdict(
        same_game=0.95,
        scorebug_in_crop=0.95,
        pair_matches_ticket=0.95,
        legal_transition=0.95,
        hud_kind="live_hud",
        hud_confidence=0.95,
        has_ticket=True,
        gate_reason="implausible_transition",
        pair_differs=False,
    )
    assert out["action"] == "blank"
    assert out["licenses_digits"] is False


class _DummyBus:
    def __init__(self) -> None:
        self._cb = None
        self.emitted = []

    def subscribe_raw(self, cb):
        self._cb = cb

        def _unsub():
            self._cb = None

        return _unsub

    def emit(self, rec):
        self.emitted.append(rec)
        if self._cb:
            self._cb(rec)


class _Evt:
    def __init__(self, payload):
        self.type = "visual"
        self.payload = payload
        self.clock_ns = 1
        self.source_lobe = "visual"


def test_on_event_only_enqueues(tmp_path, monkeypatch):
    asked = {"n": 0}

    def _ask(state):
        asked["n"] += 1
        raise AssertionError("system_one must not run on the event path")

    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        ticket_fn=lambda: {"has_ticket": True, "home_score": 21, "away_score": 7},
        live_fn=lambda: {"hud_kind": "no_board"},
        ask_fn=_ask,
    )
    try:
        t0 = time.perf_counter()
        for _ in range(64):
            bus.emit(_Evt({"parsed": {"home_score": None, "away_score": None}}))
        assert time.perf_counter() - t0 < 1.0
        assert sen._queue.qsize() > 0
        assert asked["n"] == 0
    finally:
        sen.stop()


def test_worker_never_emits_bus_events(tmp_path):
    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        ticket_fn=lambda: {
            "has_ticket": True,
            "home_score": 21,
            "away_score": 7,
            "home_team": "LOU",
            "away_team": "ND",
        },
        live_fn=lambda: {
            "home_score": None,
            "away_score": None,
            "hud_kind": "no_board",
        },
        ask_fn=lambda s: local_mint_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        stats = sen.stats()
        assert stats["judged"] >= 1
        assert stats["action"] == "observe"
        assert stats["licenses_digits"] is False
        last = sen.last()
        assert last.get("plane") == "qoresence-observation"
    finally:
        sen.stop()
