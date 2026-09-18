"""TicketGlass v0 — observation plane, fail-closed.

Locks in: enqueue-only hot path, never emits bus events, never consults the
ticket book on the event path, never licenses digits, board_paint_block cannot
unlock ConfirmTicket paint, fallback dark, --play / default OFF.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from dataclasses import fields

from qoresence.core.unified_config import (
    RetinaUnifiedConfig,
    TicketGlassConfig,
)
from qoresence.observability.ticket_glass import (
    TicketGlassSentinel,
    compose_glass_verdict,
    local_glass_answers,
    make_ticket_glass_from_config,
)
from qoresence.observability.ticket_glass_questions import (
    CLIP_NOW,
    CONF_CUT,
    GLASS_ROUTES,
    MOMENT_CLASSES,
    PAINT_BLOCK_ACT,
    PAINT_BLOCK_NOT,
    ticket_glass_questions,
)


def _sentinel(tmp_path, **kw):
    cfg = TicketGlassConfig(enabled=True, out_dir=str(tmp_path), cadence_s=0.05)
    return TicketGlassSentinel(cfg, **kw)


def _in_game_state(**board_extra):
    board = {
        "score_vlm_locked": True,
        "digit_integrity_reason": "ok",
        "ticket_stale": {
            "stale_class": "fresh",
            "action": "observe",
            "gate_reason": None,
            "freshness": 2.0,
        },
    }
    board.update(board_extra)
    return {
        "clock_ns": 1,
        "frame_seq": 1,
        "intent": {
            "play": True,
            "lens_opacity_request": 0.0,
            "mobile_connected": False,
            "x_live": False,
        },
        "title": {"plane": "in_game", "profile": "madden", "locked": True},
        "board": board,
        "situation": {"quarter": 4, "clock": "0:28", "down": 3, "distance": 7, "ticketed": True},
        "hid": {"source": "usb_play", "edges_last_n": ["x"], "apm": 40.0, "stick_heat": 0.4},
        "outcome": {"last_events": []},
        "foundry": {"ring_fill": 0.5, "window_s": 8.0, "clip_worthy_features": {}},
    }


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
    def __init__(self, payload, typ="visual"):
        self.type = typ
        self.payload = payload
        self.clock_ns = 1
        self.source_lobe = "visual"


def test_default_off():
    assert TicketGlassConfig().enabled is False
    assert make_ticket_glass_from_config(TicketGlassConfig()) is None
    names = {f.name for f in fields(RetinaUnifiedConfig)}
    assert "ticket_glass" in names


def test_play_alone_does_not_enable():
    """--play must not flip TicketGlass on (flag/env remain opt-in)."""
    text = Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "--ticket-glass" in text
    assert "QORESENCE_TICKET_GLASS=1" in text
    # The --play wiring block must not set ticket_glass.enabled.
    play_idx = text.find('if getattr(args, "play", False):')
    assert play_idx > 0
    play_block = text[play_idx : play_idx + 12000]
    assert "ticket_glass" not in play_block


def test_compose_never_licenses_digits():
    for route in GLASS_ROUTES:
        out = compose_glass_verdict(
            title_in_game=0.95,
            board_paint_block=0.05,
            moment_class="clutch",
            moment_confidence=0.95,
            clip_now="hold",
            clip_confidence=0.95,
            lens_tension=3,
            tension_confidence=0.95,
            glass_route=route,
            route_confidence=0.95,
            score_vlm_locked=True,
        )
        assert out["licenses_digits"] is False
        assert out["paint_unlocked"] is False
        assert out["foundry_cut"] is False
        assert "digits" not in out


def test_gates_observe_soft_act():
    observe = compose_glass_verdict(
        title_in_game=0.8,
        board_paint_block=0.1,
        moment_class="clutch",
        moment_confidence=0.2,
        clip_now="hold",
        clip_confidence=0.2,
        lens_tension=3,
        tension_confidence=0.2,
        glass_route="lens",
        route_confidence=0.2,
        score_vlm_locked=True,
    )
    assert observe["bands"]["glass_route"] == "observe"
    assert observe["glass_route"] == "dark"
    assert observe["glyphs"]["tension"] == 0
    assert observe["glyphs"]["cut"] == "off"

    soft = compose_glass_verdict(
        title_in_game=0.8,
        board_paint_block=0.1,
        moment_class="build",
        moment_confidence=0.55,
        clip_now="hold",
        clip_confidence=0.55,
        lens_tension=2,
        tension_confidence=0.55,
        glass_route="lens",
        route_confidence=0.55,
        score_vlm_locked=True,
    )
    assert soft["bands"]["glass_route"] == "soft"
    assert soft["glass_route"] == "dark"  # glyphs only, no route act
    assert soft["glyphs"]["tension"] == 2
    assert soft["lens_opacity"] == 0.0
    assert soft["glyphs"]["cut"] == "off"

    act = compose_glass_verdict(
        title_in_game=0.85,
        board_paint_block=0.1,
        moment_class="build",
        moment_confidence=0.8,
        clip_now="hold",
        clip_confidence=0.8,
        lens_tension=2,
        tension_confidence=0.8,
        glass_route="lens",
        route_confidence=0.8,
        score_vlm_locked=True,
    )
    assert act["bands"]["glass_route"] == "act"
    assert act["glass_route"] == "lens"
    assert act["glyphs"]["tension"] == 2
    assert act["lens_opacity"] > 0
    assert act["licenses_digits"] is False


def test_board_paint_block_cannot_unlock():
    """false / low noul never unlocks ConfirmTicket paint."""
    unlocked_board = compose_glass_verdict(
        title_in_game=0.99,
        board_paint_block=0.01,
        moment_class="clutch",
        moment_confidence=0.99,
        clip_now="cut_foundry",
        clip_confidence=0.99,
        lens_tension=3,
        tension_confidence=0.99,
        glass_route="lens",
        route_confidence=0.99,
        score_vlm_locked=False,
    )
    assert unlocked_board["licenses_digits"] is False
    assert unlocked_board["paint_unlocked"] is False
    assert unlocked_board["glyphs"]["lock"] != "open"
    assert unlocked_board["foundry_cut"] is False

    already_locked = compose_glass_verdict(
        title_in_game=0.99,
        board_paint_block=0.01,
        moment_class="clutch",
        moment_confidence=0.99,
        clip_now="hold",
        clip_confidence=0.99,
        lens_tension=1,
        tension_confidence=0.99,
        glass_route="deck_only",
        route_confidence=0.99,
        score_vlm_locked=True,
        ticket_stale_action="observe",
        ticket_stale_class="fresh",
    )
    # Observational "open" of an already-ticketed board is not a grant.
    assert already_locked["glyphs"]["lock"] == "open"
    assert already_locked["licenses_digits"] is False
    assert already_locked["paint_unlocked"] is False


def test_board_paint_block_true_forces_block_and_kills_cut():
    """Unlicensed high noul still blocks; cut stays off without block_clear."""
    out = compose_glass_verdict(
        title_in_game=0.95,
        board_paint_block=0.9,
        moment_class="clutch",
        moment_confidence=0.95,
        clip_now="cut_foundry",
        clip_confidence=0.99,
        lens_tension=3,
        tension_confidence=0.95,
        glass_route="lens",
        route_confidence=0.95,
        score_vlm_locked=False,
        ticket_stale_class="fresh",
    )
    assert out["glyphs"]["lock"] == "blocked"
    assert out["paint_block"] == "block"
    assert out["glyphs"]["cut"] == "off"
    assert out["clip_now"] == "hold"
    assert out["licenses_digits"] is False
    assert out["paint_unlocked"] is False

    # Licensed: high noul is observational — lock stays open; cut still needs clear.
    licensed = compose_glass_verdict(
        title_in_game=0.95,
        board_paint_block=0.9,
        moment_class="clutch",
        moment_confidence=0.95,
        clip_now="cut_foundry",
        clip_confidence=0.99,
        lens_tension=3,
        tension_confidence=0.95,
        glass_route="lens",
        route_confidence=0.95,
        score_vlm_locked=True,
        ticket_stale_class="fresh",
    )
    assert licensed["glyphs"]["lock"] == "open"
    assert licensed["paint_block"] == "watch"
    assert licensed["glyphs"]["cut"] == "off"
    assert licensed["licenses_digits"] is False
    assert licensed["paint_unlocked"] is False


def test_cut_foundry_needs_triple_gate():
    base = {
        "title_in_game": 0.8,
        "board_paint_block": 0.1,
        "moment_class": "clutch",
        "moment_confidence": 0.9,
        "clip_now": "cut_foundry",
        "clip_confidence": 0.9,
        "lens_tension": 3,
        "tension_confidence": 0.9,
        "glass_route": "lens",
        "route_confidence": 0.9,
        "score_vlm_locked": True,
        "ticket_stale_action": "observe",
        "ticket_stale_class": "fresh",
    }
    ok = compose_glass_verdict(**base)
    assert ok["glyphs"]["cut"] == "on"
    assert ok["clip_now"] == "cut_foundry"
    assert ok["foundry_cut"] is False  # advisory glyph only
    assert ok["licenses_digits"] is False

    low_conf = compose_glass_verdict(**{**base, "clip_confidence": 0.8})
    assert 0.8 < CONF_CUT
    assert low_conf["glyphs"]["cut"] == "off"

    low_title = compose_glass_verdict(**{**base, "title_in_game": 0.5})
    assert low_title["glyphs"]["cut"] == "off"

    watch_block = compose_glass_verdict(**{**base, "board_paint_block": 0.5})
    assert watch_block["glyphs"]["cut"] == "off"
    assert watch_block["paint_block"] == "watch"


def test_ambiguous_title_routes_dark():
    out = compose_glass_verdict(
        title_in_game=0.5,
        board_paint_block=0.1,
        glass_route="lens",
        route_confidence=0.95,
        score_vlm_locked=True,
    )
    assert out["glass_route"] == "dark"


def test_fallback_dark():
    answers = local_glass_answers({})
    assert answers["glass_route"] == "dark"
    assert answers["clip_now"] == "hold"
    assert answers["lens_tension"] == 0.0
    assert answers["moment_class"] == "unknown"
    out = compose_glass_verdict(
        title_in_game=answers["title_in_game"],
        board_paint_block=answers["board_paint_block"],
        moment_class=answers["moment_class"],
        moment_confidence=answers["moment_confidence"],
        clip_now=answers["clip_now"],
        clip_confidence=answers["clip_confidence"],
        lens_tension=answers["lens_tension"],
        tension_confidence=answers["tension_confidence"],
        glass_route=answers["glass_route"],
        route_confidence=answers["route_confidence"],
        score_vlm_locked=False,
    )
    assert out["glass_route"] == "dark"
    assert out["glyphs"]["cut"] == "off"
    assert out["glyphs"]["tension"] == 0
    assert out["glyphs"]["lock"] != "open"
    assert out["licenses_digits"] is False
    assert out["foundry_cut"] is False


def test_fallback_reuses_ticket_stale_facts():
    answers = local_glass_answers(
        {
            "title": {"plane": "in_game", "locked": True},
            "board": {
                "score_vlm_locked": True,
                "digit_integrity_reason": "ticket_stale",
                "ticket_stale": {
                    "stale_class": "crop_moved_on",
                    "action": "flag_stale",
                    "gate_reason": "crop_mismatch",
                    "freshness": 0.0,
                },
            },
        }
    )
    assert answers["board_paint_block"] >= 0.7
    assert answers["glass_route"] == "dark"
    out = compose_glass_verdict(
        title_in_game=answers["title_in_game"],
        board_paint_block=answers["board_paint_block"],
        moment_class=answers["moment_class"],
        moment_confidence=answers["moment_confidence"],
        clip_now=answers["clip_now"],
        clip_confidence=answers["clip_confidence"],
        lens_tension=answers["lens_tension"],
        tension_confidence=answers["tension_confidence"],
        glass_route=answers["glass_route"],
        route_confidence=answers["route_confidence"],
        score_vlm_locked=True,
        ticket_stale_action="flag_stale",
        ticket_stale_class="crop_moved_on",
    )
    assert out["glyphs"]["lock"] == "blocked"
    assert out["paint_unlocked"] is False
    assert out["licenses_digits"] is False



def test_licensed_crop_moved_on_watch_holds_open():
    """crop_moved_on + watch must not blank digits while ConfirmTicket licensed."""
    out = compose_glass_verdict(
        title_in_game=0.9,
        board_paint_block=0.1,
        moment_class="build",
        moment_confidence=0.8,
        clip_now="hold",
        clip_confidence=0.9,
        lens_tension=1,
        tension_confidence=0.8,
        glass_route="deck_only",
        route_confidence=0.8,
        score_vlm_locked=True,
        ticket_stale_action="watch",
        ticket_stale_class="crop_moved_on",
    )
    assert out["glyphs"]["lock"] == "open"
    assert out["paint_block"] == "clear"
    assert out["licenses_digits"] is False
    assert out["paint_unlocked"] is False
    assert out["foundry_cut"] is False


def test_licensed_crop_moved_on_watch_sticky_across_ticks():
    """Repeated crop churn ticks stay open while licensed (no ~2s flip-flop)."""
    kwargs = {
        "title_in_game": 0.85,
        "board_paint_block": 0.12,
        "score_vlm_locked": True,
        "ticket_stale_action": "watch",
        "ticket_stale_class": "crop_moved_on",
        "glass_route": "dark",
        "route_confidence": 0.9,
        "clip_now": "hold",
        "clip_confidence": 0.9,
        "lens_tension": 0,
        "tension_confidence": 0.9,
    }
    locks = [compose_glass_verdict(**kwargs)["glyphs"]["lock"] for _ in range(5)]
    assert locks == ["open"] * 5
    assert all(
        compose_glass_verdict(**kwargs)["licenses_digits"] is False for _ in range(3)
    )


def test_unlicensed_crop_moved_on_still_blocks():
    out = compose_glass_verdict(
        title_in_game=0.9,
        board_paint_block=0.1,
        score_vlm_locked=False,
        ticket_stale_action="watch",
        ticket_stale_class="crop_moved_on",
    )
    assert out["glyphs"]["lock"] == "blocked"
    assert out["licenses_digits"] is False


def test_flag_stale_and_hard_classes_still_fail_closed_when_licensed():
    base = {
        "title_in_game": 0.9,
        "board_paint_block": 0.1,
        "score_vlm_locked": True,
        "clip_now": "hold",
        "clip_confidence": 0.9,
        "glass_route": "dark",
        "route_confidence": 0.9,
    }
    flagged = compose_glass_verdict(
        **base,
        ticket_stale_action="flag_stale",
        ticket_stale_class="crop_moved_on",
    )
    assert flagged["glyphs"]["lock"] == "blocked"

    match = compose_glass_verdict(
        **base,
        ticket_stale_action="watch",
        ticket_stale_class="match_changed",
    )
    assert match["glyphs"]["lock"] == "blocked"

    menu = compose_glass_verdict(
        **base,
        ticket_stale_action="watch",
        ticket_stale_class="menu_or_plate",
    )
    assert menu["glyphs"]["lock"] == "blocked"


def test_local_glass_licensed_crop_watch_stays_below_paint_act():
    """Heuristic must not thrash PAINT_BLOCK_ACT on licensed crop churn."""
    answers = local_glass_answers(
        {
            "title": {"plane": "in_game", "locked": True},
            "board": {
                "score_vlm_locked": True,
                "digit_integrity_reason": "ok",
                "ticket_stale": {
                    "stale_class": "crop_moved_on",
                    "action": "watch",
                    "gate_reason": "crop_mismatch",
                    "freshness": 0.4,
                },
            },
        }
    )
    assert answers["board_paint_block"] < PAINT_BLOCK_ACT
    assert answers["board_paint_block"] > PAINT_BLOCK_NOT  # watch band, not clear grant
    out = compose_glass_verdict(
        title_in_game=answers["title_in_game"],
        board_paint_block=answers["board_paint_block"],
        moment_class=answers["moment_class"],
        moment_confidence=answers["moment_confidence"],
        clip_now=answers["clip_now"],
        clip_confidence=answers["clip_confidence"],
        lens_tension=answers["lens_tension"],
        tension_confidence=answers["tension_confidence"],
        glass_route=answers["glass_route"],
        route_confidence=answers["route_confidence"],
        score_vlm_locked=True,
        ticket_stale_action="watch",
        ticket_stale_class="crop_moved_on",
    )
    # Mid-band paint → watch; sticky licensed hold keeps lock open (no blanking).
    assert out["paint_block"] == "watch"
    assert out["glyphs"]["lock"] == "open"
    assert out["licenses_digits"] is False
    assert out["paint_unlocked"] is False


def test_licensed_high_paint_noul_holds_open_on_crop_watch():
    """Licensed + block_noul=0.9 + crop_moved_on/watch → lock open (not blocked)."""
    out = compose_glass_verdict(
        title_in_game=0.9,
        board_paint_block=0.9,
        score_vlm_locked=True,
        ticket_stale_action="watch",
        ticket_stale_class="crop_moved_on",
    )
    assert out["glyphs"]["lock"] == "open"
    assert out["paint_block"] == "watch"
    assert out["licenses_digits"] is False
    assert out["paint_unlocked"] is False


def test_unlicensed_high_paint_noul_still_blocks():
    out = compose_glass_verdict(
        title_in_game=0.9,
        board_paint_block=0.9,
        score_vlm_locked=False,
        ticket_stale_action="watch",
        ticket_stale_class="crop_moved_on",
    )
    assert out["glyphs"]["lock"] == "blocked"
    assert out["paint_block"] == "block"
    assert out["licenses_digits"] is False


def test_flag_stale_blocks_even_with_high_or_low_paint_when_licensed():
    """flag_stale remains fail-closed under licensed paint hold."""
    for noul in (0.1, 0.9):
        out = compose_glass_verdict(
            title_in_game=0.9,
            board_paint_block=noul,
            score_vlm_locked=True,
            ticket_stale_action="flag_stale",
            ticket_stale_class="crop_moved_on",
        )
        assert out["glyphs"]["lock"] == "blocked"
        assert out["licenses_digits"] is False



def test_sanitize_drops_pixels_and_truth_plane():
    from qoresence.observability.ticket_glass import _sanitize

    raw = {
        "title": {"plane": "in_game"},
        "jpeg": "not-a-frame",
        "frame": b"xxx",
        "qortroller": {"wrap": True},
        "truth": {"claim": True},
        "board": {"score_vlm_locked": False, "crop_jpeg": "abc"},
    }
    clean = _sanitize(raw)
    assert "jpeg" not in clean
    assert "frame" not in clean
    assert "qortroller" not in clean
    assert "truth" not in clean
    assert "crop_jpeg" not in clean["board"]
    assert clean["title"]["plane"] == "in_game"


def test_hot_path_only_enqueues_and_never_reads_ticket_book(tmp_path):
    """_on_event must not consult the ticket book (lobe lock) at all."""

    def _boom(_state=None):
        raise AssertionError("ticket book touched on event path")

    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        ticket_fn=_boom,
        state_fn=_boom,
        ask_fn=_boom,
    )
    try:
        t0 = time.perf_counter()
        for _ in range(64):
            bus.emit(_Evt({"parsed": {"home_score": 7, "away_score": 0}}))
        assert time.perf_counter() - t0 < 1.0
        assert sen._queue.qsize() > 0
        src = Path("qoresence/observability/ticket_glass.py").read_text(encoding="utf-8")
        on_event = src.split("def _on_event", 1)[1].split("def _drain_live", 1)[0]
        assert "get_ticket_book" not in on_event
        assert "licensed_last_confirm" not in on_event
    finally:
        sen.stop()


def test_worker_never_emits_bus_events(tmp_path):
    bus = _DummyBus()
    sen = _sentinel(
        tmp_path,
        bus=bus,
        state_fn=lambda: _in_game_state(),
        ask_fn=lambda s: local_glass_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        stats = sen.stats()
        assert stats["judged"] >= 1
        assert stats["licenses_digits"] is False
        assert stats["paint_unlocked"] is False
        assert stats["foundry_cut"] is False
        assert stats["glass_route"] == "dark"
        assert all(ev is not None for ev in bus.emitted)
        last = sen.last()
        assert last.get("plane") == "qoresence-observation"
        assert last.get("glyphs", {}).get("cut") == "off"
    finally:
        sen.stop()


def test_jsonl_audit_written(tmp_path):
    sen = _sentinel(
        tmp_path,
        state_fn=lambda: _in_game_state(),
        ask_fn=lambda s: local_glass_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        sen.stop()
        path = tmp_path / "ticket_glass.jsonl"
        assert path.exists()
        row = json.loads(path.read_text().strip().splitlines()[0])
        assert row["licenses_digits"] is False
        assert row["paint_unlocked"] is False
        assert row["foundry_cut"] is False
        assert set(row["glyphs"]) == {"lock", "tension", "cut"}
    finally:
        sen.stop()


def test_disabled_by_default_flag_only(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_TICKET_GLASS", raising=False)
    sen = TicketGlassSentinel(
        TicketGlassConfig(enabled=False, out_dir=str(tmp_path))
    )
    assert sen.enabled is False
    sen._on_event(_Evt({"parsed": {"home_score": 1, "away_score": 0}}))
    assert sen._queue.qsize() == 0
    sen.stop()


def test_env_enables(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.setenv("QORESENCE_TICKET_GLASS", "1")
    sen = TicketGlassSentinel(
        TicketGlassConfig(enabled=False, out_dir=str(tmp_path), cadence_s=0.05)
    )
    try:
        assert sen.enabled is True
    finally:
        sen.stop()


def test_jev_umbrella_enables_make(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_TICKET_GLASS", raising=False)
    cfg = TicketGlassConfig(enabled=False, out_dir=str(tmp_path), cadence_s=0.05)
    sen = make_ticket_glass_from_config(cfg, jev_enabled=True)
    try:
        assert sen is not None
        assert sen.enabled is True
    finally:
        if sen is not None:
            sen.stop()


def test_source_never_emits_or_cuts():
    src = Path("qoresence/observability/ticket_glass.py").read_text(encoding="utf-8")
    assert "emit_raw" not in src
    assert "bus.emit" not in src
    assert "get_clip_buffer().export" not in src
    qsrc = Path("qoresence/observability/ticket_glass_questions.py").read_text(
        encoding="utf-8"
    )
    assert "digits_ok" not in qsrc
    assert "licenses_digits" in qsrc


def test_questions_ids_when_sdk_present():
    qs = ticket_glass_questions()
    if not qs:
        return
    assert set(qs) == {
        "title_in_game",
        "board_paint_block",
        "moment_class",
        "clip_now",
        "lens_tension",
        "glass_route",
    }


def test_health_stats_shape(tmp_path):
    sen = _sentinel(
        tmp_path,
        state_fn=lambda: _in_game_state(),
        ask_fn=lambda s: local_glass_answers(s),
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and sen.stats()["judged"] == 0:
            time.sleep(0.02)
        stats = sen.stats()
        assert stats["enabled"] is True
        assert stats["licenses_digits"] is False
        assert stats["paint_unlocked"] is False
        assert stats["foundry_cut"] is False
        assert "lock" in stats["glyphs"]
        assert "tension" in stats["glyphs"]
        assert "cut" in stats["glyphs"]
    finally:
        sen.stop()


def test_closed_option_sets():
    assert "unknown" in MOMENT_CLASSES
    assert "hold" in CLIP_NOW
    assert "cut_foundry" in CLIP_NOW
    assert "dark" in GLASS_ROUTES
    assert "x_live_overlay" in GLASS_ROUTES


def test_typesafe_ask_cadence_reuses_answers(tmp_path, monkeypatch):
    """Situation ticks stay fast; TypeSafe asks only on ask_interval."""
    monkeypatch.setenv("QORESENCE_TICKET_GLASS_ASK_S", "10")
    sen = _sentinel(tmp_path, state_fn=lambda: _in_game_state(), ask_fn=None)
    try:
        sen._ask_interval_s = 10.0
        counted = {"n": 0}

        def _fake_try(_state):
            counted["n"] += 1
            return {
                "title_in_game": 0.9,
                "board_paint_block": 0.1,
                "moment_class": "build",
                "moment_confidence": 0.85,
                "clip_now": "hold",
                "clip_confidence": 0.9,
                "lens_tension": 2.0,
                "tension_confidence": 0.85,
                "glass_route": "deck_only",
                "route_confidence": 0.85,
                "source": "typesafe",
            }

        sen._try_typesafe = _fake_try  # type: ignore[method-assign]
        a1 = sen._answers_with_typesafe_cadence(_in_game_state())
        a2 = sen._answers_with_typesafe_cadence(_in_game_state())
        assert a1 is not None and a1["source"] == "typesafe"
        assert a2 is not None and a2["source"] == "typesafe"
        assert counted["n"] == 1
        assert sen.stats()["licenses_digits"] is False
    finally:
        sen.stop()


def test_typesafe_failure_falls_back_to_local(tmp_path):
    sen = _sentinel(tmp_path, state_fn=lambda: _in_game_state(), ask_fn=None)
    try:
        sen._ask_interval_s = 0.0
        sen._try_typesafe = lambda _s: None  # type: ignore[method-assign]
        answers = sen._answers_with_typesafe_cadence(_in_game_state())
        assert answers is None
        verdict = sen._judge(_in_game_state())
        assert verdict["source"] == "local_heuristic"
        assert verdict["licenses_digits"] is False
        assert verdict["glass_route"] == "dark"
    finally:
        sen.stop()
