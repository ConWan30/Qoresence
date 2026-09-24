"""Clip excision — Span Referee, Triple Proof, cut policy, Cut Receipt."""

from __future__ import annotations

import cv2
import numpy as np

from qoresence.vision import clip_excise as cx


def _jpeg(value: int) -> bytes:
    img = np.full((72, 128, 3), value, dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _vlm(t, *, clock="2:14", paused_raw=True, prompt=None, has_teams=True):
    return {
        "t_s": t,
        "clock": clock,
        "quarter": 4,
        "has_teams": has_teams,
        "paused_raw": paused_raw,
        "prompt": prompt,
    }


def _pause_evidence(**over):
    ev = {
        "duration_s": 20.0,
        "segments": [
            {
                "t0_s": 0.0,
                "t1_s": 5.0,
                "hud_kind": "live_hud",
                "confidence": "hi",
                "true_pause": "no",
            },
            {
                "t0_s": 5.0,
                "t1_s": 12.0,
                "hud_kind": "pause",
                "confidence": "hi",
                "true_pause": "yes",
            },
            {
                "t0_s": 12.0,
                "t1_s": 20.0,
                "hud_kind": "live_hud",
                "confidence": "hi",
                "true_pause": "no",
            },
        ],
        "vlm": [
            _vlm(4.0, paused_raw=False),
            _vlm(6.0),
            _vlm(8.5),
            _vlm(11.0),
            _vlm(13.0, paused_raw=False, prompt="snap"),
        ],
        "inputs": [{"t_s": 4.8, "name": "options", "kind": "press"}],
        "marks": [],
        "still_runs": [[5.2, 11.9]],
    }
    ev.update(over)
    return ev


def test_stillness_series_detects_frozen_picture():
    frames = [(i * 0.1, _jpeg(40 if i < 10 else (i * 17) % 255)) for i in range(30)]
    series = cx.stillness_series(frames, hz=10)
    assert series and all(d <= cx.STILL_DIFF_MAX for t, d in series if t < 0.95)
    runs = cx.still_runs(series, min_s=0.5)
    assert runs and runs[0][0] == 0.0 and runs[0][1] >= 0.8
    assert all(r[1] < 1.1 for r in runs)


def test_still_runs_requires_min_length():
    series = [(0.1, 0.0), (0.2, 0.0), (0.3, 9.0), (0.4, 0.0)]
    assert cx.still_runs(series, min_s=0.5) == []


def test_candidate_spans_merge_segment_and_still():
    spans = cx.build_candidate_spans(_pause_evidence())
    assert len(spans) == 1
    s = spans[0]
    assert (s.t0_s, s.t1_s) == (5.0, 12.0)
    assert s.kinds == ["pause", "still"]
    assert s.confidence == "hi" and s.true_pause == "yes"
    ev = s.evidence
    assert ev["options_press_before_s"] == 0.2
    assert ev["vlm_before"]["paused_raw"] is False and ev["vlm_after"]["prompt"] == "snap"
    assert len(ev["vlm_inside"]) == 3 and ev["still_s"] > 6.0
    assert ev["ticket_overlap"] is False


def test_candidate_spans_cap_and_min_length():
    segs = [
        {"t0_s": float(i * 3), "t1_s": float(i * 3 + 2), "hud_kind": "menu", "confidence": "hi"}
        for i in range(20)
    ] + [{"t0_s": 70.0, "t1_s": 71.0, "hud_kind": "menu"}]
    ev = {"duration_s": 80.0, "segments": segs, "still_runs": []}
    spans = cx.build_candidate_spans(ev)
    assert len(spans) == cx.MAX_SPANS
    assert all(s.length_s >= cx.MIN_SPAN_S for s in spans)


def test_candidate_span_ticket_overlap():
    ev = _pause_evidence(marks=[{"t_s": 7.0, "kind": "confirm_clip"}])
    s = cx.build_candidate_spans(ev)[0]
    assert s.evidence["ticket_overlap"] is True
    assert s.evidence["chapter_marks_inside"] == ["confirm_clip"]


def test_triple_proof_truth_table():
    s = cx.build_candidate_spans(_pause_evidence())[0]
    ok, reasons = cx.triple_proof(s)
    assert ok and {"paused_raw", "still", "clock_frozen", "options_press"} <= set(reasons)

    no_still = cx.build_candidate_spans(_pause_evidence(still_runs=[]))[0]
    assert cx.triple_proof(no_still)[0] is False

    moving_clock = _pause_evidence(
        vlm=[_vlm(6.0, clock="2:14"), _vlm(8.5, clock="2:09"), _vlm(11.0, clock="2:05")],
        inputs=[],
    )
    assert cx.triple_proof(cx.build_candidate_spans(moving_clock)[0])[0] is False

    options_only = _pause_evidence(vlm=[_vlm(6.0, clock=None), _vlm(9.0, clock=None)])
    assert cx.triple_proof(cx.build_candidate_spans(options_only)[0])[0] is True

    not_paused = _pause_evidence(vlm=[_vlm(6.0), _vlm(9.0, paused_raw=False)])
    assert cx.triple_proof(cx.build_candidate_spans(not_paused)[0])[0] is False


def test_referee_state_names_spans_and_carries_no_digits():
    spans = cx.build_candidate_spans(_pause_evidence())
    state = cx.referee_state(spans, game_profile="madden_26")
    assert state["spans"][0]["id"] == "s0"
    assert "home_score" not in str(state) and "away_score" not in str(state)
    assert "Never license score digits" in state["policy"]


def test_referee_uses_ask_fn_and_skips_when_no_spans():
    seen = {}

    def ask(state, spans):
        seen["n"] = len(state["spans"])
        return {s.id: {"kind": "pause", "kind_confidence": 0.9} for s in spans}, "jev-test"

    spans = cx.build_candidate_spans(_pause_evidence())
    answers, model = cx.run_referee(spans, ask_fn=ask)
    assert seen["n"] == 1 and model == "jev-test" and answers["s0"]["kind"] == "pause"
    assert cx.run_referee([], ask_fn=ask) == ({}, None)


def test_referee_without_sdk_or_key_returns_none(monkeypatch):
    monkeypatch.setattr(cx, "referee_questions", lambda spans: {})
    spans = cx.build_candidate_spans(_pause_evidence())
    assert cx.run_referee(spans) == (None, None)


def test_parse_referee_response_closed_vocabulary():
    class A:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    spans = cx.build_candidate_spans(_pause_evidence())
    resp = A(
        choices={"s0_kind": A(choice="not_a_kind", confidence=0.9)},
        nouls={"s0_suspended": A(noul=0.91), "s0_hides_play": A(noul=0.05)},
    )
    out = cx.parse_referee_response(resp, spans)["s0"]
    assert out["kind"] is None and out["suspended"] == 0.91 and out["hides_play"] == 0.05


def test_excise_default_off(monkeypatch):
    monkeypatch.delenv("QORESENCE_CLIP_EXCISE", raising=False)
    cx.set_enabled(None)
    assert cx.excise_enabled() is False
    monkeypatch.setenv("QORESENCE_CLIP_EXCISE", "1")
    assert cx.excise_enabled() is True
    cx.set_enabled(False)
    assert cx.excise_enabled() is False
    cx.set_enabled(None)


def test_module_never_touches_the_bus():
    import inspect

    src = inspect.getsource(cx)
    assert "emit_raw" not in src and "subscribe" not in src
