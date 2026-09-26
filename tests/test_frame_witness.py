"""Frame witness: plate text names the situation. No network."""

from __future__ import annotations

import threading
import time

import pytest

from qoresence.sync.coupling_ticket import mint_coupling_ticket
from qoresence.vision.frame_witness import (
    FrameEvidence,
    collapse_witness_spans,
    publish_witness,
    public_witness,
    reset_witness_for_tests,
    resolve_witness,
    samples_in_window,
    witness_blocks_heat,
    witness_kind,
    witness_tick,
)


@pytest.fixture(autouse=True)
def _clean_witness():
    reset_witness_for_tests()
    yield
    reset_witness_for_tests()


def test_resume_with_score_pair_is_pause():
    kind = witness_kind(
        FrameEvidence(
            profile="madden_27",
            plate_text="RESUME RAIDERS 14 SAINTS 0 1:47 4TH",
            scorebug=True,
        )
    )
    assert kind == "pause"


def test_press_any_button_is_menu():
    assert (
        witness_kind(
            FrameEvidence(profile="ncaa_football_27", plate_text="PRESS ANY BUTTON")
        )
        == "menu"
    )


def test_progress_plate_is_loading():
    assert (
        witness_kind(
            FrameEvidence(
                profile="madden_27",
                plate_text="YOUR PROGRESS QUICK MATCH ADVANCE",
            )
        )
        == "loading"
    )


def test_kickoff_clock_is_play_not_loading():
    kind = witness_kind(
        FrameEvidence(profile="madden_27", plate_text="KICKOFF 4:00", scorebug=True)
    )
    assert kind == "play"


def test_play_call_with_clock_is_play():
    kind = witness_kind(
        FrameEvidence(
            profile="madden_27",
            plate_text="4TH AND 9 PLAY CALL 1:47",
            scorebug=True,
        )
    )
    assert kind == "play"


def test_conflict_abstains():
    assert (
        witness_kind(
            FrameEvidence(profile="madden_27", plate_text="RESUME PRESS ANY BUTTON")
        )
        == "abstain"
    )


def test_silence_and_unknown_profile_abstain():
    assert witness_kind(FrameEvidence(profile="madden_27", plate_text="")) == "abstain"
    assert (
        witness_kind(FrameEvidence(profile="call_of_duty", plate_text="RESUME"))
        == "abstain"
    )


def test_paused_raw_without_play_call_is_pause():
    assert (
        witness_kind(
            FrameEvidence(profile="madden_27", paused_raw=True, scorebug=True, plate_text="1:47")
        )
        == "pause"
    )


def test_optical_hit_does_not_ask_noul():
    calls: list[dict] = []

    def ask(state: dict) -> str:
        calls.append(state)
        return "menu"

    kind, source = resolve_witness(
        FrameEvidence(profile="madden_27", plate_text="RESUME"),
        noul=True,
        ask=ask,
    )
    assert (kind, source) == ("pause", "optical")
    assert calls == []


def test_noul_only_on_abstain_and_miss_stores_none():
    kind, source = resolve_witness(
        FrameEvidence(profile="madden_27", plate_text=""),
        noul=True,
        ask=lambda _state: "loading",
    )
    assert (kind, source) == ("loading", "noul")
    kind, source = resolve_witness(
        FrameEvidence(profile="madden_27", plate_text=""),
        noul=True,
        ask=lambda _state: None,
    )
    assert (kind, source) == ("abstain", "none")
    kind, source = resolve_witness(
        FrameEvidence(profile="madden_27", plate_text=""),
        noul=False,
        ask=lambda _state: "pause",
    )
    assert (kind, source) == ("abstain", "none")


def test_inflight_noul_is_not_preempted():
    started = threading.Event()
    release = threading.Event()

    def ask(_state: dict) -> str:
        started.set()
        assert release.wait(2)
        return "pause"

    worker = threading.Thread(
        target=lambda: resolve_witness(
            FrameEvidence(profile="madden_27"),
            noul=True,
            ask=ask,
        )
    )
    worker.start()
    assert started.wait(1)
    kind, source = resolve_witness(
        FrameEvidence(profile="madden_27"),
        noul=True,
        ask=lambda _state: "menu",
    )
    assert (kind, source) == ("abstain", "busy")
    release.set()
    worker.join(2)
    assert not worker.is_alive()


def test_stale_witness_does_not_rename():
    publish_witness("pause", "optical", mono=time.monotonic() - 5, frame_seq=3, clock_ns=9)
    stale = public_witness()
    assert stale["fresh"] is False
    assert stale["kind"] == "abstain"
    assert stale["source"] == "none"
    publish_witness("menu", "optical", frame_seq=4, clock_ns=10)
    fresh = public_witness()
    assert fresh["fresh"] is True
    assert fresh["kind"] == "menu"
    assert fresh["source"] == "optical"


def test_tick_publishes_without_a_bus():
    got = witness_tick(
        FrameEvidence(profile="madden_27", plate_text="QUICK PLAY"),
        noul=False,
    )
    assert got["kind"] == "menu"
    assert got["fresh"] is True
    assert witness_blocks_heat() is True


def test_not_play_witness_refuses_heat():
    publish_witness("pause", "optical")
    assert witness_blocks_heat() is True
    assert (
        mint_coupling_ticket(
            clock_ns=time.monotonic_ns(),
            frame_seq=9,
            phrase="SPRINT",
            coupling=0.4,
            hold_energy=1.1,
            pll_lock=True,
            video_fresh=True,
        )
        is None
    )
    publish_witness("play", "optical")
    ticket = mint_coupling_ticket(
        clock_ns=time.monotonic_ns(),
        frame_seq=10,
        phrase="SPRINT",
        coupling=0.4,
        hold_energy=1.1,
        pll_lock=True,
        video_fresh=True,
    )
    assert ticket is not None


def _sample(t, kind, source="optical", seq=1):
    return {"t_s": t, "kind": kind, "source": source, "frame_seq": seq}


def test_collapse_keeps_a_pause_until_play_and_drops_a_short_one():
    spans = collapse_witness_spans(
        [
            _sample(0.0, "pause", seq=1),
            _sample(1.0, "pause", seq=2),
            _sample(2.0, "play", seq=3),
        ]
    )
    assert spans == [
        {"t0_s": 0.0, "t1_s": 2.0, "kind": "pause", "source": "optical"},
    ]
    short = collapse_witness_spans([_sample(0.0, "pause"), _sample(1.0, "play")])
    assert short == []


def test_collapse_splits_kinds_and_abstain_breaks():
    spans = collapse_witness_spans(
        [
            _sample(0.0, "pause"),
            _sample(1.0, "pause"),
            _sample(2.0, "menu"),
            _sample(3.0, "menu"),
            _sample(4.0, "menu"),
            _sample(5.0, "play"),
        ]
    )
    assert [s["kind"] for s in spans] == ["pause", "menu"]
    assert spans[0]["t1_s"] == 2.0
    assert spans[1]["t0_s"] == 2.0 and spans[1]["t1_s"] == 5.0
    broken = collapse_witness_spans(
        [
            _sample(0.0, "loading"),
            _sample(1.0, "abstain"),
            _sample(2.0, "loading"),
        ]
    )
    assert broken == []


def test_tape_slices_the_clip_window():
    t0 = 5_000.0
    publish_witness("pause", "optical", frame_seq=8, clock_ns=80, mono=t0)
    publish_witness("pause", "optical", frame_seq=9, clock_ns=90, mono=t0 + 1)
    publish_witness("play", "optical", frame_seq=10, clock_ns=100, mono=t0 + 2)
    publish_witness("menu", "optical", frame_seq=11, clock_ns=110, mono=t0 + 30)
    rows = samples_in_window(int(t0 * 1e9), int((t0 + 2) * 1e9))
    assert [r["kind"] for r in rows] == ["pause", "pause", "play"]
    assert rows[0]["t_s"] == 0.0
    assert rows[0]["frame_seq"] == 8
    assert rows[2]["t_s"] == 2.0
