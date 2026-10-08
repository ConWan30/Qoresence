"""Local scorebug: multi-frame agreement, cloud cross-check, flag, service gates."""

from __future__ import annotations

import pytest

from qoresence.sync.digit_integrity import CONFIRM_DIGIT_MAX_AGE_NS
from qoresence.vision.local_scorebug import (
    AgreementWindow,
    FrameRead,
    LocalScorebugService,
    ScorebugReader,
    choose_board,
    local_scorebug_enabled,
    local_scorebug_flag,
)
from qoresence.vision.local_scorebug.agreement import AgreementConfig
from tests.local_scorebug_helpers import frame_from_band

MS = 1_000_000


def _read(left: int, right: int, quarter: int = 2, clock: int = 90) -> FrameRead:
    return FrameRead(
        ok=True,
        reason="ok",
        profile_id="madden27_standard",
        left_score=left,
        right_score=right,
        quarter=quarter,
        clock_seconds=clock,
        clock_text=f"{clock // 60}:{clock % 60:02d}",
    )


BLANK = FrameRead(ok=False, reason="score_unsure", profile_id="madden27_standard")


def _offer(w: AgreementWindow, read: FrameRead, t_ms: int, session: str = "s1", crop: str = "c"):
    return w.offer(read, clock_ns=t_ms * MS, crop_hash=crop, session_id=session)


def test_needs_three_spaced_reads():
    w = AgreementWindow()
    assert not _offer(w, _read(14, 7), 1000).agreed
    assert not _offer(w, _read(14, 7), 1250).agreed
    r = _offer(w, _read(14, 7), 1500)
    assert r.agreed and r.run == 3 and r.read.pair == (14, 7)
    assert (r.first_ns, r.last_ns) == (1000 * MS, 1500 * MS)


def test_reads_too_close_are_not_new_evidence():
    w = AgreementWindow()
    for t in (1000, 1050, 1100, 1150, 1199):
        assert not _offer(w, _read(14, 7), t).agreed
    assert w.state.samples and len(w.state.samples) == 1


def test_span_must_reach_min():
    w = AgreementWindow(AgreementConfig(need=3, min_interval_ns=100 * MS, min_span_ns=400 * MS))
    _offer(w, _read(14, 7), 1000)
    _offer(w, _read(14, 7), 1100)
    assert not _offer(w, _read(14, 7), 1200).agreed  # 3 reads, 200 ms span
    assert _offer(w, _read(14, 7), 1400).agreed


def test_blank_resets_run():
    w = AgreementWindow()
    _offer(w, _read(14, 7), 1000)
    _offer(w, _read(14, 7), 1250)
    assert _offer(w, BLANK, 1500).reason == "score_unsure"
    assert not _offer(w, _read(14, 7), 1750).agreed
    assert not _offer(w, _read(14, 7), 2000).agreed
    assert _offer(w, _read(14, 7), 2250).agreed


def test_different_pair_or_quarter_restarts():
    w = AgreementWindow()
    _offer(w, _read(14, 7), 1000)
    _offer(w, _read(14, 7), 1250)
    assert not _offer(w, _read(14, 0), 1500).agreed
    assert not _offer(w, _read(14, 0, quarter=3), 1750).agreed
    assert w.state.samples and len(w.state.samples) == 1


def test_game_clock_running_backwards_restarts():
    w = AgreementWindow()
    _offer(w, _read(14, 7, clock=90), 1000)
    _offer(w, _read(14, 7, clock=89), 1250)
    assert not _offer(w, _read(14, 7, clock=95), 1500).agreed  # clock went up: new run
    assert len(w.state.samples) == 1


def test_long_gap_and_session_change_restart():
    w = AgreementWindow()
    _offer(w, _read(14, 7), 1000)
    _offer(w, _read(14, 7), 1250)
    assert not _offer(w, _read(14, 7), 5000).agreed  # > 2 s gap
    w2 = AgreementWindow()
    _offer(w2, _read(14, 7), 1000)
    _offer(w2, _read(14, 7), 1250)
    assert not _offer(w2, _read(14, 7), 1500, session="s2").agreed


def test_empty_crop_hash_refused():
    w = AgreementWindow()
    for t in (1000, 1250, 1500, 1750):
        r = _offer(w, _read(14, 7), t, crop="")
        assert not r.agreed and r.reason == "empty_crop_hash"


def test_suspicious_jump_needs_nine_reads_over_two_seconds():
    w = AgreementWindow()
    for t in (1000, 1250, 1500):
        last = _offer(w, _read(14, 7), t)
    assert last.agreed
    # 14-7 -> 10-7 is a drop: re-read for longer before offering it.
    t = 2000
    results = []
    for _ in range(9):
        results.append(_offer(w, _read(10, 7), t))
        t += 250
    assert all(r.suspicious for r in results)
    assert not any(r.agreed for r in results[:-1])
    assert results[-1].agreed and results[-1].run == 9


def test_plausible_score_change_needs_only_three():
    w = AgreementWindow()
    for t in (1000, 1250, 1500):
        _offer(w, _read(14, 7), t)
    _offer(w, _read(14, 10), 2000)
    _offer(w, _read(14, 10), 2250)
    r = _offer(w, _read(14, 10), 2500)
    assert r.agreed and not r.suspicious


# ---- cloud cross-check ------------------------------------------------------


def _local(left=14, right=7, since=1000):
    return {
        "left_score": left,
        "right_score": right,
        "home_score": right,
        "away_score": left,
        "_source": "local_scorebug",
        "local": {"pair_since_ns": since},
    }


def test_choose_board_cases():
    cloud = {"home_score": 7, "away_score": 14, "_observation": {"clock_ns": 5000}}
    assert choose_board(None, cloud) == (cloud, "cloud")
    assert choose_board(None, None) == (None, "none")
    b, why = choose_board(_local(), None)
    assert why == "local" and b["_source"] == "local_scorebug"
    assert choose_board(_local(), cloud)[1] == "local_cloud_agree"
    wrong = {"home_score": 3, "away_score": 14, "_observation": {"clock_ns": 5000}}
    assert choose_board(_local(), wrong) == (None, "cross_check_disagree")
    stale = {"home_score": 3, "away_score": 14, "_observation": {"clock_ns": 500}}
    assert choose_board(_local(since=1000), stale)[1] == "local_newer_than_cloud"
    lr = {"left_score": 14, "right_score": 7}
    assert choose_board(_local(), lr)[1] == "local_cloud_agree"
    assert choose_board(_local(), {"visible_control": {"button": "A"}})[1] == "local"


# ---- flag -------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,flag,enabled",
    [
        (None, "default", True),
        ("1", "forced_on", True),
        ("on", "forced_on", True),
        ("0", "forced_off", False),
        ("false", "forced_off", False),
        ("maybe", "default", True),
    ],
)
def test_flag(monkeypatch, value, flag, enabled):
    if value is None:
        monkeypatch.delenv("QORESENCE_LOCAL_SCOREBUG", raising=False)
    else:
        monkeypatch.setenv("QORESENCE_LOCAL_SCOREBUG", value)
    assert local_scorebug_flag() == flag
    assert local_scorebug_enabled() is enabled


# ---- service ----------------------------------------------------------------


@pytest.fixture(scope="module")
def reader() -> ScorebugReader:
    return ScorebugReader()


def _observe(svc, frame, t_ms, seq, session="s1", now_ms=None):
    return svc.observe(
        frame,
        stamp={"seq": seq, "clock_ns": t_ms * MS, "crop_hash": "crop-ok"},
        session_id=session,
        game_state="gameplay",
        game_profile="madden_27",
        home_left=False,
        now_ns=(now_ms if now_ms is not None else t_ms) * MS,
    )


def test_service_locks_after_agreement_and_shapes_board(reader):
    svc = LocalScorebugService(reader)
    f = frame_from_band("std_29_15_4th_2-38")
    assert _observe(svc, f, 1000, 1) is None
    assert _observe(svc, f, 1250, 2) is None
    b = _observe(svc, f, 1500, 3)
    assert b is not None
    assert (b["left_score"], b["right_score"]) == (29, 15)
    assert (b["home_score"], b["away_score"]) == (15, 29)  # home on the right
    assert b["quarter"] == 4 and b["clock"] == "2:38" and b["clock_seconds"] == 158
    assert b["_source"] == "local_scorebug"
    assert b["_model"].startswith("local_scorebug_v1:")
    obs = b["_observation"]
    assert (
        obs["clock_ns"] == 1500 * MS and obs["crop_hash"] == "crop-ok" and obs["session_id"] == "s1"
    )
    assert b["local"]["agree_n"] == 3
    st = svc.stats()
    assert st["state"] == "sure" and st["agreed"] == 1 and st["reads"] == 3


def test_service_same_frame_seq_is_not_new_evidence(reader):
    svc = LocalScorebugService(reader)
    f = frame_from_band("std_14_7_2nd_1-23")
    for t in (1000, 1250, 1500, 1750):
        assert _observe(svc, f, t, seq=7) is None
    assert svc.stats()["reads"] == 1


def test_service_blank_frames_never_lock(reader):
    svc = LocalScorebugService(reader)
    for name in ("dark_skin", "cfb", "std_red_clock", "std_touchdown_banner", "no_scorebug"):
        f = frame_from_band(name)
        for i in range(6):
            assert _observe(svc, f, 1000 + 300 * i, seq=f"{name}{i}") is None
    assert svc.stats()["agreed"] == 0


def test_service_sure_board_expires_after_8s_and_on_session_change(reader):
    svc = LocalScorebugService(reader)
    f = frame_from_band("std_14_7_2nd_1-23")
    for i, t in enumerate((1000, 1250, 1500)):
        b = _observe(svc, f, t, i)
    assert b is not None
    # Same frame again (no new evidence): still sure while the read frame is fresh.
    assert _observe(svc, f, 1500, 2, now_ms=3000) is not None
    old_ms = 1500 + CONFIRM_DIGIT_MAX_AGE_NS // MS + 1
    assert _observe(svc, f, 1500, 2, now_ms=old_ms) is None
    assert _observe(svc, f, 1500, 2, session="other", now_ms=3000) is None


def test_service_missing_pack_stays_blank(monkeypatch, tmp_path):
    from qoresence.vision.local_scorebug import service as svc_mod

    def boom(*a, **k):
        raise FileNotFoundError("pack missing")

    monkeypatch.setattr(svc_mod, "ScorebugReader", boom)
    svc = LocalScorebugService()
    f = frame_from_band("std_14_7_2nd_1-23")
    for i, t in enumerate((1000, 1250, 1500, 1750)):
        assert _observe(svc, f, t, i) is None
    assert "pack missing" in svc.stats()["reader_error"]
