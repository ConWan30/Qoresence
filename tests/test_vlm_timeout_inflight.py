"""VLM timeout / inflight / menu+scorebug schedule regressions."""

from __future__ import annotations

import threading
import time

import numpy as np

from qoresence.vision.scoreboard_vlm import (
    ScoreboardVlmReferee,
    _GAMEPLAY_INTERVAL_S,
    _HTTP_TIMEOUT_S,
    _INFLIGHT_WATCHDOG_S,
    _MENU_INTERVAL_S,
    _QUICKSILVER_SLOT_WAIT_S,
    _TIMEOUT_BACKOFF_MAX_S,
)
from qoresence.agents.quicksilver_slot import acquire_quicksilver
from tests.scorebug_fixtures import licensed_scorebug_frame


def _wait_inflight_clear(ref: ScoreboardVlmReferee, timeout_s: float = 3.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        with ref._lock:
            if not ref._inflight:
                return
        time.sleep(0.02)
    raise AssertionError("inflight did not clear in time")


def test_read_timeout_clears_inflight_and_allows_next_schedule(monkeypatch):
    """Quicksilver Read timeout must release inflight so the next tick can run."""
    import requests

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref._last_call = 0.0

    def _timeout(*_a, **_k):
        raise requests.exceptions.ReadTimeout("Read timed out")

    monkeypatch.setattr("requests.post", _timeout)
    frame = licensed_scorebug_frame()

    ref.schedule(frame, force=True, game_state="gameplay", game_profile="cfb_27")
    _wait_inflight_clear(ref)

    with ref._lock:
        assert ref._inflight is False
        assert ref._timeout_count == 1
        assert ref._skip_inflight_count == 0

    stats = ref.stats()
    assert stats["inflight"] is False
    assert stats["timeout_count"] == 1
    assert stats["http_timeout_s"] == _HTTP_TIMEOUT_S
    assert stats["inflight_watchdog_s"] == _INFLIGHT_WATCHDOG_S

    ref._last_call = time.time() - (_GAMEPLAY_INTERVAL_S + 1.0)
    with ref._lock:
        ref._timeout_backoff_until = 0.0
    ref.schedule(frame, force=False, game_state="gameplay", game_profile="cfb_27")
    _wait_inflight_clear(ref)

    with ref._lock:
        assert ref._inflight is False
        assert ref._timeout_count == 2
        assert ref._skip_inflight_count == 0


def test_timeout_backoff_capped_so_seqgate_can_refresh():
    """Exponential 60s backoff starved confirm tickets past the 8s SEQGATE window."""
    assert _TIMEOUT_BACKOFF_MAX_S <= 2.0
    ref = ScoreboardVlmReferee()
    now = time.time()
    for _ in range(8):
        ref._on_read_timeout()
    with ref._lock:
        wait = ref._timeout_backoff_until - now
        last_call = ref._last_call
    assert wait <= _TIMEOUT_BACKOFF_MAX_S + 0.5
    assert last_call == 0.0


def _licensed_confirm_crop() -> np.ndarray:
    frame = licensed_scorebug_frame()
    crop = ScoreboardVlmReferee._crop(frame, game_state="menu", game_profile="cfb_27")
    assert crop is not None
    return crop


def test_menu_with_scorebug_crop_uses_gameplay_interval_not_menu_starved(monkeypatch):
    """Misclassified menu + live scorebug must not wait the 8s menu interval."""
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    called = threading.Event()

    def _noop_vlm(_crop):
        called.set()
        return None

    monkeypatch.setattr(ref, "_call_vlm", _noop_vlm)
    monkeypatch.setattr(ref, "_crop", lambda *a, **k: _licensed_confirm_crop())
    frame = licensed_scorebug_frame()
    # 7s ago: inside menu interval (8s) but past gameplay interval (6s).
    ref._last_call = time.time() - 7.0

    ref.schedule(
        frame,
        game_state="menu",
        game_profile="generic_arcade",
        game_title="",
        reason="tick",
    )
    assert called.wait(timeout=2.0), "menu+scorebug must schedule at gameplay cadence"
    _wait_inflight_clear(ref)

    with ref._lock:
        assert ref._skip_interval_count == 0


def test_cfb_profile_uses_gameplay_interval_on_menu(monkeypatch):
    """Football profile must not use menu interval even when game_state=menu."""
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    called = threading.Event()

    monkeypatch.setattr(ref, "_call_vlm", lambda _c: called.set())
    frame = licensed_scorebug_frame()
    ref._last_call = time.time() - 7.0

    ref.schedule(
        frame,
        game_state="menu",
        game_profile="cfb_27",
        game_title="EA SPORTS College Football 27",
        reason="tick",
    )
    assert called.wait(timeout=2.0)
    _wait_inflight_clear(ref)


def test_menu_without_scorebug_still_uses_menu_interval(monkeypatch):
    """Plain menu hub with no scorebug keeps the sparse menu cadence."""
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    called = []

    monkeypatch.setattr(ref, "_call_vlm", lambda _c: called.append(1))
    monkeypatch.setattr(ref, "_crop", lambda *a, **k: np.zeros((96, 200, 3), dtype=np.uint8))
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    ref._last_call = time.time() - 7.0

    ref.schedule(frame, game_state="menu", game_profile="generic_arcade", reason="tick")

    time.sleep(0.1)
    with ref._lock:
        assert ref._inflight is False
        assert called == []
        assert ref._skip_interval_count == 1


def test_read_timeout_skips_urllib_fallback(monkeypatch):
    """requests Read timeout must not fall through to urllib (double POST storm)."""
    from unittest.mock import patch

    import requests

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"

    monkeypatch.setattr(
        "requests.post",
        lambda *_a, **_k: (_ for _ in ()).throw(requests.exceptions.ReadTimeout()),
    )
    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    crop[:, :60] = 255
    crop[:, 140:] = 255

    with patch("urllib.request.urlopen") as urlopen:
        assert ref._call_vlm(crop) is None
        urlopen.assert_not_called()


def test_timeout_null_does_not_mint_zero_zero(monkeypatch):
    """Read timeout → null last; never invent 0-0 on the glass path."""
    import requests

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref._last = {"home_score": 10, "away_score": 7, "quarter": 3}
    ref._last_result_ts = time.time()

    monkeypatch.setattr(
        "requests.post",
        lambda *_a, **_k: (_ for _ in ()).throw(requests.exceptions.ReadTimeout()),
    )
    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    crop[:, :60] = 255
    crop[:, 140:] = 255

    assert ref._call_vlm(crop) is None
    assert ref.get_last() is None

    parsed = ScoreboardVlmReferee._parse_json(
        '{"home_score": null, "away_score": null, "quarter": 1}'
    )
    assert parsed is not None
    assert parsed["home_score"] is None
    assert parsed["away_score"] is None


def test_stats_exposes_timeout_inflight_skip_counters():
    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref._timeout_count = 3
    ref._skip_inflight_count = 5
    ref._skip_interval_count = 2
    ref._inflight = True
    ref._inflight_since = time.time() - 1.5

    stats = ref.stats()
    assert stats["timeout_count"] == 3
    assert stats["skip_inflight_count"] == 5
    assert stats["skip_interval_count"] == 2
    assert stats["inflight"] is True
    assert stats["inflight_age_s"] is not None
    assert stats["inflight_age_s"] >= 1.0
    assert stats["http_timeout_s"] == _HTTP_TIMEOUT_S
    assert stats["inflight_watchdog_s"] == _HTTP_TIMEOUT_S + 2.0


def test_scoreboard_vlm_slot_busy_clears_inflight_without_long_wait(monkeypatch):
    """Confirm path must not sit inflight for 14s while waiting on Quicksilver."""
    import threading

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    gate = threading.Event()

    def holder() -> None:
        with acquire_quicksilver(2.0) as ok:
            assert ok is True
            gate.wait(2.0)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    time.sleep(0.05)
    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    crop[:, :60] = 255
    crop[:, 140:] = 255
    t0 = time.monotonic()
    assert ref._call_vlm(crop) is None
    elapsed = time.monotonic() - t0
    assert elapsed < 0.25, "slot busy must skip quickly, not block on 14s acquire"
    assert _QUICKSILVER_SLOT_WAIT_S == 0.05
    gate.set()
    t.join(1.0)


def test_empty_http_200_clears_inflight_and_allows_next_schedule(monkeypatch):
    """HTTP 200 with empty content must not stick inflight or block the next read."""
    from unittest.mock import MagicMock

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref._last_call = 0.0
    refreshed: list[int] = []

    def _empty_200(*_a, **_k):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        }
        return resp

    monkeypatch.setattr("requests.post", _empty_200)
    monkeypatch.setattr(
        "qoresence.vision.scoreboard_vlm._refresh_confirm_clock_after_200",
        lambda: refreshed.append(1),
    )
    frame = licensed_scorebug_frame()

    ref.schedule(frame, force=True, game_state="gameplay", game_profile="cfb_27")
    _wait_inflight_clear(ref)

    with ref._lock:
        assert ref._inflight is False
        assert ref._skip_inflight_count == 0
        assert ref._last is None
        assert ref._last_http_status == 200
    assert refreshed, "empty HTTP 200 must refresh confirm clock"
    assert ref.stats()["has_result"] is False

    called: list[int] = []
    monkeypatch.setattr(ref, "_call_vlm", lambda _c: called.append(1))
    ref._last_call = time.time() - (_GAMEPLAY_INTERVAL_S + 1.0)
    ref.schedule(frame, force=False, game_state="gameplay", game_profile="cfb_27")
    deadline = time.time() + 2.0
    while time.time() < deadline and not called:
        time.sleep(0.02)
    assert called, "next schedule must run after empty HTTP 200 clears inflight"
    _wait_inflight_clear(ref)


def test_empty_http_200_refreshes_licensed_confirm_clock(monkeypatch):
    """Empty 200 still bumps ticket clock so SEQGATE does not go ticket_stale."""
    from unittest.mock import MagicMock

    from qoresence.vision.confirm_ticket import get_ticket_book, licensed_last_confirm, mint_confirm_ticket

    book = get_ticket_book()
    book.clear()
    ticket = mint_confirm_ticket(
        session_id="s",
        clock_ns=1_000_000_000,
        home_score=7,
        away_score=0,
        crop_hash="crop-ok",
        book=book,
    )
    book.put(ticket, home_team="HOME", away_team="AWAY")

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"

    def _empty_200(*_a, **_k):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        }
        return resp

    monkeypatch.setattr("requests.post", _empty_200)
    monkeypatch.setattr(
        "qoresence.monitor.frame_hub.get_latest_stamp",
        lambda: {"clock_ns": 5_000_000_000, "seq": 42},
    )
    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    crop[:, :60] = 255
    crop[:, 140:] = 255

    assert ref._call_vlm(crop) is None
    last = licensed_last_confirm(book)
    assert last is not None
    assert last.clock_ns == 5_000_000_000
    assert last.home_score == 7
    assert last.away_score == 0


def test_empty_http_200_does_not_mint_zero_zero(monkeypatch):
    """Empty parse after HTTP 200 must not invent 0-0 on the glass path."""
    from unittest.mock import MagicMock

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    ref._last = {"home_score": 10, "away_score": 7, "quarter": 3}

    def _empty_200(*_a, **_k):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        }
        return resp

    monkeypatch.setattr("requests.post", _empty_200)
    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    crop[:, :60] = 255
    crop[:, 140:] = 255

    assert ref._call_vlm(crop) is None
    last = ref.get_last()
    assert last is not None
    assert (last.get("home_score"), last.get("away_score")) == (10, 7)


def test_inflight_heartbeat_keeps_ticket_fresh_during_slow_post(monkeypatch):
    """Licensed ticket must not go ticket_stale mid-POST while live clock advances."""
    import threading
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    from qoresence.sync.digit_integrity import CONFIRM_DIGIT_MAX_AGE_NS, digit_void_reason
    from qoresence.vision import scoreboard_vlm
    from qoresence.vision.confirm_ticket import (
        get_ticket_book,
        licensed_last_confirm,
        mint_confirm_ticket,
    )

    book = get_ticket_book()
    book.clear()
    ticket = mint_confirm_ticket(
        session_id="s",
        clock_ns=1_000_000_000,
        home_score=13,
        away_score=31,
        crop_hash="bug",
        frame_seq=10,
        book=book,
    )
    book.put(ticket, home_team="NO", away_team="CIN")
    live_clock = {"ns": 1_000_000_000}

    monkeypatch.setattr(
        "qoresence.monitor.frame_hub.get_latest_stamp",
        lambda: {"clock_ns": live_clock["ns"], "seq": 42},
    )
    monkeypatch.setattr(scoreboard_vlm, "_CONFIRM_HEARTBEAT_INTERVAL_S", 0.05)

    post_started = threading.Event()

    def slow_post(*_a, **_k):
        post_started.set()
        time.sleep(0.35)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        }
        return resp

    @contextmanager
    def always_acquire(_wait_s: float):
        yield True

    monkeypatch.setattr("qoresence.agents.quicksilver_slot.acquire_quicksilver", always_acquire)
    monkeypatch.setattr("requests.post", slow_post)

    ref = ScoreboardVlmReferee()
    ref.enabled = True
    ref._api_key = "test_key"
    crop = np.zeros((96, 200, 3), dtype=np.uint8)
    crop[:, :60] = 255
    crop[:, 140:] = 255

    def run_with_heartbeat() -> None:
        with scoreboard_vlm._confirm_clock_heartbeat_while_inflight():
            ref._call_vlm(crop)

    worker = threading.Thread(target=run_with_heartbeat, name="slow-vlm-post", daemon=True)
    worker.start()
    assert post_started.wait(timeout=2.0), "VLM POST should start"
    live_clock["ns"] += int(CONFIRM_DIGIT_MAX_AGE_NS * 1.5)
    time.sleep(0.25)

    last = licensed_last_confirm(book)
    assert last is not None
    assert last.ticket_id == ticket.ticket_id
    assert (last.home_score, last.away_score) == (13, 31)
    reason = digit_void_reason(
        confirm_ticket_id=last.ticket_id,
        score_vlm_locked=True,
        ticket_crop_hash=last.crop_hash,
        live_crop_hash=last.crop_hash,
        same_seq=True,
        ticket_clock_ns=last.clock_ns,
        live_clock_ns=live_clock["ns"],
    )
    assert reason == "licensed"

    worker.join(timeout=3.0)
    book.clear()


def test_inflight_heartbeat_skips_without_licensed_ticket(monkeypatch):
    """No licensed ticket → heartbeat is a no-op (no mint, no crash)."""
    from qoresence.vision import scoreboard_vlm
    from qoresence.vision.confirm_ticket import get_ticket_book

    book = get_ticket_book()
    book.clear()
    ticks: list[int] = []
    monkeypatch.setattr(
        scoreboard_vlm,
        "_refresh_confirm_clock_from_framehub",
        lambda: ticks.append(1),
    )

    with scoreboard_vlm._confirm_clock_heartbeat_while_inflight():
        time.sleep(0.05)

    assert ticks == []


def test_health_payload_shape_matches_deck_scoreboard_vlm_stats():
    """Same fields /health uses via get_scoreboard_vlm().stats()."""
    from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

    ref = get_scoreboard_vlm()
    ref._timeout_count = 1
    ref._skip_inflight_count = 2
    ref._skip_interval_count = 3
    ref._inflight = False

    vlm = ref.stats()
    assert vlm["timeout_count"] == 1
    assert vlm["skip_inflight_count"] == 2
    assert vlm["skip_interval_count"] == 3
    assert vlm["inflight"] is False
    assert vlm["menu_interval_s"] == _MENU_INTERVAL_S
