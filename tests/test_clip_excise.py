"""Clip excision — Span Referee, Triple Proof, cut policy, Cut Receipt."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
import pytest

from qoresence.vision import clip_excise as cx
from qoresence.vision.clip_buffer import HdmiClipBuffer


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
    ok, reasons = cx.triple_proof(s, game_profile="madden_27")
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


def test_frozen_clock_proof_is_football_only():
    clock_only = cx.build_candidate_spans(_pause_evidence(inputs=[]))[0]
    assert cx.triple_proof(clock_only, game_profile="madden_27")[0] is True
    assert cx.triple_proof(clock_only, game_profile="cfb_27")[0] is True
    assert cx.triple_proof(clock_only, game_profile="valorant")[0] is False
    assert cx.triple_proof(clock_only)[0] is False
    assert cx.cut_policy(clock_only, None) == ("keep", "offline_no_proof")
    assert cx.cut_policy(clock_only, None, game_profile="madden_27")[0] == "cut"


def test_current_game_profile_uses_operator_pin(monkeypatch, tmp_path):
    monkeypatch.setenv("QORESENCE_LAST_PROFILE_PATH", str(tmp_path / "none"))
    monkeypatch.delenv("QORESENCE_GAME_PROFILE", raising=False)
    assert cx.current_game_profile() is None
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "madden_27")
    assert cx.current_game_profile() == "madden_27"
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "not a game")
    assert cx.current_game_profile() is None


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


# --------------------------------------------------------------------------- policy


def _span(**ev_over):
    s = cx.build_candidate_spans(_pause_evidence())[0]
    s.evidence.update(ev_over)
    return s


def _ans(kind="pause", conf=0.93, suspended=0.91, hides=0.05):
    return {
        "s0": {"kind": kind, "kind_confidence": conf, "suspended": suspended, "hides_play": hides}
    }


def test_policy_table():
    s = _span()
    assert cx.cut_policy(s, _ans())[0] == "cut"
    assert cx.cut_policy(s, _ans(conf=0.7))[0] == "suggest"
    assert cx.cut_policy(s, _ans(suspended=0.6))[0] == "suggest"
    assert cx.cut_policy(s, _ans(suspended=0.5))[0] == "suggest"
    assert cx.cut_policy(s, _ans(suspended=0.49))[0] == "keep"
    assert cx.cut_policy(s, _ans(conf=0.55))[0] == "keep"
    assert cx.cut_policy(s, _ans(hides=0.3)) == ("keep", "may_hide_play")
    assert cx.cut_policy(s, _ans(hides=None))[0] == "keep"
    assert cx.cut_policy(s, _ans(kind="unknown"))[0] == "keep"
    assert cx.cut_policy(s, _ans(kind="gameplay"))[0] == "keep"
    assert cx.cut_policy(s, _ans(kind="menu", suspended=None))[0] == "cut"
    assert cx.cut_policy(s, _ans(kind="loading", conf=0.7))[0] == "suggest"
    assert cx.cut_policy(s, _ans(kind="replay_or_cutscene", conf=0.99))[0] == "suggest"
    assert cx.cut_policy(s, {})[0] == "keep"


def test_policy_hard_keeps_beat_confident_referee():
    assert cx.cut_policy(_span(ticket_overlap=True), _ans()) == ("keep", "ticket_or_mark_inside")


def test_policy_offline_cuts_only_triple_proof_pause():
    assert cx.cut_policy(_span(), None)[0] == "cut"
    assert cx.cut_policy(_span(still_s=0.4), None) == ("keep", "offline_no_proof")
    menu_ev = _pause_evidence(
        segments=[{"t0_s": 5.0, "t1_s": 12.0, "hud_kind": "menu", "confidence": "hi"}],
        vlm=[_vlm(6.0, paused_raw=False), _vlm(9.0, paused_raw=False)],
    )
    assert cx.cut_policy(cx.build_candidate_spans(menu_ev)[0], None)[0] == "keep"


def test_plan_cuts_pads_and_time_map_round_trip():
    rows = [{"id": "s0", "t0_s": 5.0, "t1_s": 12.0, "decision": "cut"}]
    cuts, keep, aborted = cx.plan_cuts(rows, 20.0)
    assert not aborted
    assert cuts == [[5.4, 11.6]]
    assert keep == [[0.0, 5.4], [11.6, 20.0]]
    tmap = cx.time_map(keep)
    assert tmap == [[0.0, 0.0, 5.4], [5.4, 11.6, 8.4]]
    assert cx.source_time(tmap, 6.0) == 12.2
    assert cx.source_time(tmap, 2.0) == 2.0


def test_plan_cuts_aborts_when_too_much_would_go():
    rows = [{"id": "s0", "t0_s": 0.0, "t1_s": 19.0, "decision": "cut"}]
    cuts, keep, aborted = cx.plan_cuts(rows, 20.0)
    assert aborted and cuts == [] and keep == [[0.0, 20.0]]


def test_suggest_renders_as_keep_until_user_accepts():
    rows = [{"id": "s0", "t0_s": 5.0, "t1_s": 12.0, "decision": "suggest", "user": None}]
    assert cx.plan_cuts(rows, 20.0)[0] == []
    rows[0]["user"] = "cut"
    assert cx.plan_cuts(rows, 20.0)[0] == [[5.4, 11.6]]


def test_receipt_end_to_end_with_referee(tmp_path):
    mp4 = tmp_path / "hdmi_clip_x.mp4"
    mp4.write_bytes(b"x")

    def ask(state, spans):
        return _ans(), "jev-1.13.0"

    receipt = cx.plan_excision(
        mp4,
        start_ns=0,
        end_ns=int(20e9),
        duration_s=20.0,
        evidence=_pause_evidence(),
        ask_fn=ask,
        use_referee=True,
    )
    assert receipt["schema"] == cx.RECEIPT_SCHEMA
    assert receipt["referee"] == "jev" and receipt["model"] == "jev-1.13.0"
    assert receipt["excision"] == "applied" and receipt["cuts"] == [[5.4, 11.6]]
    assert receipt["edited_duration_s"] == 13.8
    assert receipt["licenses_digits"] is False
    assert receipt["spans"][0]["reason"] == "referee_pause"
    on_disk = cx.read_receipt(mp4)
    assert on_disk["cuts"] == receipt["cuts"]
    text = cx.receipt_path(mp4).read_text()
    for banned in ("highlight", "clutch", "best"):
        assert banned not in text.lower()

    assert cx.apply_user_decision(on_disk, "s0", "keep")
    assert on_disk["cuts"] == [] and on_disk["excision"] == "none"
    assert not cx.apply_user_decision(on_disk, "nope", "cut")
    assert not cx.apply_user_decision(on_disk, "s0", "maybe")


def test_receipt_offline_when_referee_unavailable(tmp_path):
    mp4 = tmp_path / "hdmi_clip_y.mp4"
    mp4.write_bytes(b"x")
    receipt = cx.plan_excision(
        mp4,
        start_ns=0,
        end_ns=int(20e9),
        duration_s=20.0,
        evidence=_pause_evidence(),
        use_referee=False,
    )
    assert receipt["referee"] == "offline_triple_proof" and receipt["model"] is None
    assert receipt["spans"][0]["reason"].startswith("triple_proof:")
    assert receipt["excision"] == "applied"


def test_receipt_no_spans_needs_no_render(tmp_path):
    mp4 = tmp_path / "hdmi_clip_z.mp4"
    mp4.write_bytes(b"x")
    ev = {"segments": [], "vlm": [], "inputs": [], "marks": [], "still_runs": []}
    receipt = cx.plan_excision(
        mp4, start_ns=0, end_ns=int(10e9), duration_s=10.0, evidence=ev, use_referee=True
    )
    assert receipt["excision"] == "none" and receipt["render"]["state"] == "not_needed"
    assert receipt["referee"] == "none"
    assert receipt["keep"] == [[0.0, 10.0]]


# --------------------------------------------------------------------------- render + wiring

needs_ffmpeg = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg not installed"
)


def _probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(r.stdout.strip())


def _noise_jpeg(seed: int) -> bytes:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (100, 160, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return buf.tobytes()


def _fill_ring(buf: HdmiClipBuffer, *, fps: float = 10.0) -> float:
    """0–3 s moving, 3–8 s frozen, 8–11 s moving. Returns first ts."""
    import time

    t0 = time.monotonic() - 12.0
    frozen = _noise_jpeg(999)
    for i in range(int(11 * fps)):
        t = i / fps
        jpg = frozen if 3.0 <= t < 8.0 else _noise_jpeg(i)
        buf._frames.append((t0 + t, jpg, 160, 100, i + 1))
    return t0


@needs_ffmpeg
def test_render_cut_ripple_deletes_ranges(tmp_path):
    src = tmp_path / "hdmi_clip_src.mp4"
    buf = HdmiClipBuffer(seconds=30, target_fps=10, max_width=160, out_dir=tmp_path)
    _fill_ring(buf)
    res = buf.export(path=src, seconds=11)
    assert res is not None and src.is_file()
    dst = tmp_path / "hdmi_clip_src.cut.mp4"
    out = HdmiClipBuffer.render_cut(src, [[0.0, 3.4], [7.6, 11.0]], dst)
    assert out["ok"] and dst.is_file()
    assert abs(_probe_duration(dst) - 6.8) < 0.4
    assert abs(_probe_duration(src) - res.duration_s) < 0.4


def test_render_cut_refuses_without_ranges(tmp_path):
    src = tmp_path / "missing.mp4"
    assert HdmiClipBuffer.render_cut(src, [], tmp_path / "x.cut.mp4")["ok"] is False


@needs_ffmpeg
def test_export_with_excise_on_cuts_proven_pause(tmp_path, monkeypatch):
    """Frozen middle + raw pause reads + same game clock + Options → offline cut."""
    monkeypatch.setenv("QORESENCE_CLIP_EXCISE", "1")
    monkeypatch.setenv("QORESENCE_GAME_PROFILE", "madden_27")
    cx.set_enabled(None)
    real_collect = cx.collect_evidence

    def collect(start_ns, end_ns, *, stillness=None):
        ev = real_collect(start_ns, end_ns, stillness=stillness)
        ev["segments"] = []
        ev["vlm"] = [_vlm(4.0), _vlm(5.5), _vlm(7.0)]
        ev["inputs"] = [{"t_s": 2.8, "name": "options", "kind": "press"}]
        ev["marks"] = []
        return ev

    monkeypatch.setattr(cx, "collect_evidence", collect)
    monkeypatch.setattr(cx, "_referee_available", lambda: False)
    buf = HdmiClipBuffer(seconds=30, target_fps=10, max_width=160, out_dir=tmp_path)
    _fill_ring(buf)
    src = tmp_path / "hdmi_clip_pause.mp4"
    res = buf.export(path=src, seconds=11)
    assert res is not None
    assert cx.get_excise_worker().drain(60)
    receipt = json.loads(cx.receipt_path(src).read_text())
    assert receipt["referee"] == "offline_triple_proof"
    assert receipt["game_profile"] == "madden_27"
    assert receipt["excision"] == "applied", receipt
    assert receipt["render"]["state"] == "done"
    span = receipt["spans"][0]
    assert span["kinds"] == ["still"] and span["reason"].startswith("triple_proof:")
    cut = cx.cut_mp4_path(src)
    assert cut.is_file() and src.is_file()
    assert _probe_duration(cut) < _probe_duration(src) - 3.0

    summary = cx.cut_summary(src)
    assert summary["render"] == "done" and summary["url"].endswith(".cut.mp4")

    assert cx.request_user_decision(src, span["id"], "keep") is not None
    assert cx.get_excise_worker().drain(60)
    after = cx.read_receipt(src)
    assert after["excision"] == "none" and after["render"]["state"] == "not_needed"
    assert not cut.exists()
    labels = cx.read_labels(cx.labels_path(src))
    assert [(r["system"], r["user"], r["game_profile"]) for r in labels] == [
        ("cut", "keep", "madden_27")
    ]
    cx.set_enabled(None)


def test_export_with_excise_off_writes_no_receipt(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_CLIP_EXCISE", raising=False)
    cx.set_enabled(None)
    calls = []
    monkeypatch.setattr(cx, "submit_excision", lambda *a, **k: calls.append(1))
    monkeypatch.setattr(
        HdmiClipBuffer,
        "_ffmpeg_h264",
        staticmethod(lambda s, d, f, a=None: d.write_bytes(b"x" * 600) or True),
    )
    buf = HdmiClipBuffer(seconds=30, target_fps=10, max_width=160, out_dir=tmp_path)
    _fill_ring(buf)
    buf.export(path=tmp_path / "hdmi_clip_off.mp4", seconds=5)
    assert calls == []
    assert not (tmp_path / "hdmi_clip_off.cut.json").exists()


def test_cut_renders_are_not_listed_as_clips(tmp_path):
    from qoresence.foundry.index import scan_clips
    from qoresence.pilot.monitor import _list_clips

    (tmp_path / "hdmi_clip_a.mp4").write_bytes(b"x")
    (tmp_path / "hdmi_clip_a.cut.mp4").write_bytes(b"x")
    clips = scan_clips(tmp_path)
    assert len(clips) == 1
    assert ".cut.mp4" not in json.dumps(clips)
    assert _list_clips(tmp_path) == {str(tmp_path / "hdmi_clip_a.mp4").replace("\\", "/")}
    assert cx.is_cut_render("clips/hdmi_clip_a.cut.mp4") and not cx.is_cut_render("hdmi_clip_a.mp4")


def test_full_queue_writes_skipped_busy_receipt(tmp_path, monkeypatch):
    class Full:
        def submit(self, kind, job):
            return False

    monkeypatch.setattr(cx, "get_excise_worker", lambda: Full())
    monkeypatch.setattr(
        cx, "collect_evidence", lambda s, e, stillness=None: {"segments": [], "still_runs": []}
    )
    mp4 = tmp_path / "hdmi_clip_busy.mp4"
    mp4.write_bytes(b"x")
    snap = [(1.0, _jpeg(10), 128, 72, 1), (2.0, _jpeg(10), 128, 72, 2)]
    assert cx.submit_excision(mp4, snapshot=snap, duration_s=1.0) is False
    assert cx.read_receipt(mp4)["excision"] == "skipped_busy"


def _deck_client(monkeypatch, tmp_path):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from qoresence.deck import server as deck_server
    from qoresence.vision import clip_buffer

    monkeypatch.setattr(clip_buffer, "DEFAULT_OUT_DIR", str(tmp_path))
    return fastapi_testclient.TestClient(deck_server.create_app(), client=("127.0.0.1", 50123))


def _write_pause_receipt(tmp_path):
    mp4 = tmp_path / "hdmi_clip_deck.mp4"
    mp4.write_bytes(b"x" * 600)
    cx.plan_excision(
        mp4,
        start_ns=0,
        end_ns=int(20e9),
        duration_s=20.0,
        evidence=_pause_evidence(),
        ask_fn=lambda state, spans: (_ans(conf=0.7), "jev-1.13.0"),
        use_referee=True,
    )
    return mp4


def test_deck_lists_cut_state_and_hides_renders(monkeypatch, tmp_path):
    client = _deck_client(monkeypatch, tmp_path)
    _write_pause_receipt(tmp_path)
    (tmp_path / "hdmi_clip_deck.cut.mp4").write_bytes(b"x" * 600)
    clips = client.get("/api/clips").json()["clips"]
    assert [c["name"] for c in clips] == ["hdmi_clip_deck.mp4"]
    assert clips[0]["cut"]["excision"] == "suggestions_only"
    assert clips[0]["cut"]["suggestions"] == 1
    assert client.get("/media/clips/hdmi_clip_deck.cut.json").status_code == 200
    assert client.get("/media/clips/hdmi_clip_deck.cut.mp4").status_code == 200


def test_deck_cut_decision_route(monkeypatch, tmp_path):
    client = _deck_client(monkeypatch, tmp_path)
    mp4 = _write_pause_receipt(tmp_path)
    queued = []

    class Worker:
        def submit(self, kind, job):
            queued.append((kind, job["mp4"]))
            return True

    monkeypatch.setattr(cx, "get_excise_worker", lambda: Worker())
    r = client.post("/api/clip/hdmi_clip_deck/cuts", json={"span_id": "s0", "decision": "cut"})
    assert r.status_code == 200 and r.json()["excision"] == "applied"
    assert r.json()["render"] == "pending"
    assert queued == [("render", str(mp4))]
    assert cx.read_receipt(mp4)["spans"][0]["user"] == "cut"

    bad = client.post("/api/clip/hdmi_clip_deck/cuts", json={"span_id": "s0", "decision": "maybe"})
    assert bad.status_code == 400
    assert client.post(
        "/api/clip/..%2Fetc/cuts", json={"span_id": "s0", "decision": "cut"}
    ).status_code in (400, 404)
    assert (
        client.post(
            "/api/clip/hdmi_clip_nope/cuts", json={"span_id": "s0", "decision": "cut"}
        ).status_code
        == 404
    )


def test_deck_cut_route_requires_loopback(monkeypatch, tmp_path):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from qoresence.deck import server as deck_server
    from qoresence.vision import clip_buffer

    monkeypatch.setattr(clip_buffer, "DEFAULT_OUT_DIR", str(tmp_path))
    _write_pause_receipt(tmp_path)
    remote = fastapi_testclient.TestClient(deck_server.create_app(), client=("10.0.0.5", 50123))
    r = remote.post("/api/clip/hdmi_clip_deck/cuts", json={"span_id": "s0", "decision": "cut"})
    assert r.status_code == 403


def test_health_sampler_and_merge():
    ages = iter([0.2, None, 0.6, 0.3, 0.3, 0.3, 0.3])
    with cx._HealthSampler(interval_s=0.01, read=lambda: next(ages, 0.3)) as s:
        import time

        time.sleep(0.05)
    summ = s.summary()
    assert summ["source"] == "frame_hub" and summ["no_frame"] == 1
    assert summ["age_s_max"] == 0.6 and summ["samples"] >= 3

    merged = cx.merge_health({"age_s_max": 0.9, "samples": 4, "no_frame": 0, "jobs": 1}, summ)
    assert merged["age_s_max"] == 0.9 and merged["jobs"] == 2
    assert merged["samples"] == 4 + summ["samples"]
    empty = cx.merge_health(None, {"age_s_max": None, "samples": 0, "no_frame": 3})
    assert empty["age_s_max"] is None and empty["jobs"] == 1


def test_worker_records_health_in_receipt(tmp_path, monkeypatch):
    mp4 = tmp_path / "hdmi_clip_h.mp4"
    mp4.write_bytes(b"x")
    monkeypatch.setattr(cx, "_hub_age_s", lambda: 0.25)
    monkeypatch.setattr(cx, "_referee_available", lambda: False)
    job = {
        "mp4": str(mp4),
        "start_ns": 0,
        "end_ns": int(20e9),
        "duration_s": 20.0,
        "evidence": _pause_evidence(segments=[], still_runs=[]),
    }
    assert cx.get_excise_worker().submit("plan", job)
    assert cx.get_excise_worker().drain(30)
    health = cx.read_receipt(mp4)["health"]
    assert health["age_s_max"] == 0.25 and health["samples"] >= 2 and health["jobs"] == 1


def _witness(*rows):
    return [
        {"t_s": t, "kind": kind, "source": "optical", "frame_seq": i + 1}
        for i, (t, kind) in enumerate(rows)
    ]


def test_witness_proposal_stays_suggest_until_accepted():
    samples = _witness((0.0, "pause"), (1.0, "pause"), (2.0, "play"))
    receipt = cx.build_receipt("c.mp4", 10.0, [], None, model_id=None, witness=samples)
    assert receipt["excision"] == "suggestions_only"
    assert receipt["cuts"] == []
    assert receipt["witness"][0]["kind"] == "pause"
    span = receipt["spans"][0]
    assert span["id"] == "w0"
    assert span["decision"] == "suggest" and span["user"] is None
    assert span["reason"] == "witness:pause"
    assert cx.effective_decision(span) == "keep"
    assert cx.apply_user_decision(receipt, span["id"], "keep") is True
    assert receipt["cuts"] == []
    assert cx.apply_user_decision(receipt, span["id"], "cut") is True
    assert receipt["cuts"]


def test_witness_does_not_duplicate_a_policy_span():
    covered = cx.Span(id="s0", t0_s=0.0, t1_s=4.0, kinds=["pause"], confidence="hi", true_pause="yes")
    samples = _witness((0.0, "pause"), (1.0, "pause"), (2.0, "play"))
    receipt = cx.build_receipt("c.mp4", 10.0, [covered], None, model_id=None, witness=samples)
    assert [r["id"] for r in receipt["spans"]] == ["s0"]


def test_witness_gap_is_a_separate_suggestion():
    early = cx.Span(id="s0", t0_s=0.0, t1_s=2.0, kinds=["still"])
    samples = _witness((4.0, "menu"), (5.0, "menu"), (6.0, "play"))
    receipt = cx.build_receipt("c.mp4", 12.0, [early], None, model_id=None, witness=samples)
    added = [r for r in receipt["spans"] if str(r["id"]).startswith("w")]
    assert len(added) == 1
    assert added[0]["decision"] == "suggest"
    assert added[0]["t0_s"] == 4.0 and added[0]["t1_s"] == 6.0
    assert cx.plan_cuts(receipt["spans"], 12.0)[0] == []
