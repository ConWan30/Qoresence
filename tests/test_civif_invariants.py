"""CIVIF fail-closed invariants — observation plane regression."""

from __future__ import annotations

import json
from typing import Any

from qoresence.core.civif_tick import build_coupled_tick
from qoresence.core.coupled_event import (
    build_coupling_sidecar,
    set_live_situation_hook,
    situation_from_live_snapshot,
)
from qoresence.foundry.cer_log import CerLog
from qoresence.foundry.civif_metrics import reset_metrics, snapshot
from qoresence.foundry.coach import coach_from_sidecar
from qoresence.foundry.highlights import get_coupled_clips, rank_highlights
from qoresence.mcp.server import handle_civif_live, handle_civif_query_clips

BUTTON_TOKENS = ("R2", "L2", "Cross", "Square", "Triangle", "Circle", "R1", "L1")


def teardown_function() -> None:
    set_live_situation_hook(None)
    reset_metrics()


def _blob(obj: Any) -> str:
    return json.dumps(obj, default=str)


def _assert_no_button_names(obj: Any) -> None:
    text = _blob(obj)
    for tok in BUTTON_TOKENS:
        assert tok not in text, f"unbodied payload leaked {tok}: {text[:400]}"


def _clip(tmp_path, stem: str, **kw: Any) -> None:
    payload = build_coupling_sidecar(
        clip_id=stem,
        session_id=kw.get("session_id", ""),
        start_ns=1_000_000_000,
        end_ns=2_000_000_000,
        frame_start=1,
        frame_end=2,
        video_path=f"{stem}.mp4",
        events=kw.get("events", []),
        coupling=kw.get("coupling", {}),
        coupling_history=[],
        situation=kw.get("situation"),
    )
    (tmp_path / f"{stem}.mp4").write_bytes(b"x")
    (tmp_path / f"{stem}.coupling.json").write_text(json.dumps(payload), encoding="utf-8")
    buttons = kw.get("buttons")
    if buttons:
        (tmp_path / f"{stem}.buttons.json").write_text(json.dumps(buttons), encoding="utf-8")


def _live_json(log: CerLog) -> dict[str, Any]:
    from qoresence.foundry import cer_log as cer_mod

    prev = cer_mod._log
    cer_mod._log = log
    try:
        return handle_civif_live()
    finally:
        cer_mod._log = prev


def test_unbodied_tick_and_live_json_hide_input():
    rec = build_coupled_tick(
        coupling={"video_clock_ns": 40, "frame_seq": 4, "imu_bodied": False, "coupling": 0.3},
        events=[],
        session_id="inv-unbodied",
    )
    d = rec.to_dict()
    assert d["controller_bodied"] is False
    assert d["input_ticks"] == []
    assert d["input"]["events"] == []
    _assert_no_button_names(d)

    log = CerLog(jsonl_path=None)
    log.observe({"video_clock_ns": 40, "frame_seq": 4, "imu_bodied": False, "coupling": 0.3})
    live = _live_json(log)
    assert live["ok"] is True
    assert live["record"]["controller_bodied"] is False
    assert live["record"]["input_ticks"] == []
    assert live["coach"]["timing"] is None
    assert live["coach"]["pattern"] is None
    assert "timing" in live["coach"]["withheld"]
    _assert_no_button_names({"record": live["record"], "coach": live["coach"]})


def test_unbodied_highlights_omit_button_names_and_pad_rank(tmp_path):
    sit = {"board_locked": True, "home_score": 10, "away_score": 7}
    coup = {"coupling": 0.6}
    _clip(tmp_path, "plain", coupling=coup, situation=sit, events=[])
    _clip(
        tmp_path,
        "named",
        coupling=coup,
        situation=sit,
        events=[],
        buttons={
            "events": [
                {"clock_ns": 1_100_000_000, "name": "R2", "kind": "press", "value": 1.0},
            ]
        },
    )
    out = rank_highlights(tmp_path, limit=8)
    by = {h["stem"]: h for h in out["hits"]}
    assert by["plain"]["controller_bodied"] is False
    assert by["named"]["controller_bodied"] is False
    assert by["plain"]["explanation"]["key_inputs"] == []
    assert by["named"]["explanation"]["key_inputs"] == []
    assert by["plain"]["score"] == by["named"]["score"]
    _assert_no_button_names(out["hits"])
    q = get_coupled_clips(clips_dir=tmp_path, controller_bodied_only=True)
    assert q["count"] == 0


def test_unlocked_board_strips_digits_everywhere(tmp_path):
    set_live_situation_hook(
        lambda: {
            "board_locked": False,
            "home_score": 99,
            "away_score": 88,
            "down": 3,
            "distance": 2,
        }
    )
    tick = build_coupled_tick(coupling={"video_clock_ns": 1, "imu_bodied": False}).to_dict()
    assert tick["board_locked"] is False
    assert tick["situation_snapshot"] is None
    sit = tick["situation"]
    assert sit["home_score"] is None
    assert sit["away_score"] is None
    snap = situation_from_live_snapshot(
        {"score_vlm_locked": False, "home_score": 21, "away_score": 14, "down": 1}
    )
    assert snap["board_locked"] is False
    assert snap["home_score"] is None

    data = build_coupling_sidecar(
        clip_id="u",
        session_id="s",
        start_ns=1,
        end_ns=2,
        frame_start=0,
        frame_end=1,
        video_path="u.mp4",
        events=[],
        coupling={"coupling": 0.4},
        coupling_history=[],
        situation={"board_locked": False, "home_score": 99, "away_score": 1},
    )
    assert data["situation"]["home_score"] is None
    assert data["situation"]["away_score"] is None

    _clip(
        tmp_path,
        "unlocked",
        coupling={"coupling": 0.7},
        situation={"board_locked": False, "home_score": 99, "away_score": 1, "clutch_kind": "td"},
        events=[],
    )
    hit = rank_highlights(tmp_path, limit=4)["hits"][0]
    assert hit["board_locked"] is False
    expl = hit["explanation"]
    assert expl["board_locked"] is False
    assert expl["situation_present"] is False
    assert expl["home_score"] is None
    assert expl["away_score"] is None
    assert expl["outcome_tag"] is None
    assert hit["civif"]["home_score"] is None
    coach = coach_from_sidecar(data)
    assert coach["situation"] is None
    assert "score" in coach["withheld"]


def test_mid_session_bodied_and_board_transitions():
    set_live_situation_hook(lambda: {"board_locked": False, "home_score": 3})
    log = CerLog(jsonl_path=None)
    log.observe({"video_clock_ns": 10, "imu_bodied": True, "coupling": 0.2})
    a = log.last()
    assert a["controller_bodied"] is True
    assert a["board_locked"] is False
    assert a["situation"]["home_score"] is None

    set_live_situation_hook(
        lambda: {"board_locked": True, "home_score": 14, "away_score": 7}
    )
    log.observe({"video_clock_ns": 20, "imu_bodied": False, "coupling": 0.2})
    b = log.last()
    assert b["controller_bodied"] is False
    assert b["input_ticks"] == []
    assert b["board_locked"] is True
    assert b["situation"]["home_score"] == 14

    set_live_situation_hook(lambda: {"board_locked": False, "home_score": 21})
    log.observe({"video_clock_ns": 30, "imu_bodied": True, "coupling": 0.2})
    c = log.last()
    assert c["controller_bodied"] is True
    assert c["board_locked"] is False
    assert c["situation"]["home_score"] is None


def test_highlight_segments_respect_bodied_flag(tmp_path):
    _clip(
        tmp_path,
        "seg_unbodied",
        coupling={"coupling": 0.8},
        events=[],
        situation={"board_locked": True, "home_score": 7, "away_score": 0},
    )
    _clip(
        tmp_path,
        "seg_bodied",
        coupling={"coupling": 0.8, "imu_bodied": True},
        events=[{"clock_ns": 1_100_000_000, "name": "R2", "kind": "press"}],
        situation={"board_locked": True, "home_score": 7, "away_score": 0},
    )
    hits = {h["stem"]: h for h in rank_highlights(tmp_path, limit=8)["hits"]}
    assert hits["seg_unbodied"]["explanation"]["key_inputs"] == []
    assert "R2" in hits["seg_bodied"]["explanation"]["key_inputs"]
    q = handle_civif_query_clips(controller_bodied_only=True, limit=8)
    assert q["ok"] is True


def test_metrics_hook_tracks_ticks_and_highlights(tmp_path):
    reset_metrics()
    log = CerLog(jsonl_path=None)
    set_live_situation_hook(lambda: {"board_locked": False})
    log.observe({"video_clock_ns": 1, "imu_bodied": False, "coupling": 0.1})
    set_live_situation_hook(lambda: {"board_locked": True, "home_score": 1, "away_score": 0})
    log.observe({"video_clock_ns": 2, "imu_bodied": True, "coupling": 0.2})
    stats = snapshot()
    rows = list(stats.values())
    assert rows
    # session_id may be empty → "_"
    tickish = [r for r in rows if r["tick_count"] >= 2]
    assert tickish
    row = tickish[0]
    assert row["board_locked_ticks"] == 1
    assert abs(row["board_locked_rate"] - 0.5) < 1e-9
    assert row["controller_bodied_any"] is True

    _clip(tmp_path, "m", coupling={"coupling": 0.55, "imu_bodied": True}, events=[])
    rank_highlights(tmp_path, limit=4)
    after = snapshot()
    hc = [r["highlight_coupling"] for r in after.values() if r["highlight_coupling"]["count"]]
    assert hc
    assert hc[0]["min"] == 0.55
    assert hc[0]["max"] == 0.55
    assert hc[0]["mean"] == 0.55


def test_civif_live_and_highlights_run_inline_not_threadpooled():
    """CIVIF page showed live unavailable because live sat on the clip thread pool."""
    import inspect

    from qoresence.deck.server import create_app

    app = create_app()
    src = ""
    for route in app.routes:
        if getattr(route, "path", None) == "/api/civif/live":
            src = inspect.getsource(route.endpoint)
            break
    assert src
    assert "asyncio.to_thread" not in src
    assert "handle_civif_live" in src


def test_civif_html_skips_live_poll_while_inflight():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "civif.html").read_text(
        encoding="utf-8"
    )
    assert "let liveInflight" in html
    assert "if (liveInflight) return" in html
    assert html.count("setInterval(tickLive") == 1


def test_civif_disk_routes_stay_threadpooled():
    """Highlights/query/clips/narrative scan clips/ — must not hitch the JPEG loop."""
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "server.py"
    ).read_text(encoding="utf-8")

    def chunk(path: str) -> str:
        key = f'@app.get("{path}")'
        start = text.index(key)
        nxt = text.find("@app.get", start + len(key))
        return text[start:nxt]

    live = chunk("/api/civif/live")
    assert "asyncio.to_thread" not in live
    assert "handle_civif_live" in live
    for path in (
        "/api/civif/highlights",
        "/api/civif/query",
        "/api/clips",
        "/api/civif/narrative",
    ):
        body = chunk(path)
        assert "asyncio.to_thread" in body, path
