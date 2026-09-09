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
)
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
