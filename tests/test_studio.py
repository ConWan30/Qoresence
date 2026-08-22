"""Tests for Ghost Cut / Foundry Bay (no generative video API)."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from qoresence.core.unified_config import (
    RetinaUnifiedConfig,
    StudioConfig,
)
from qoresence.foundry.index import is_board_dump, pick_play_chapter, score_play_chapter
from qoresence.studio.api import jobs_payload, list_candidates, resolve_clip_path, status_payload
from qoresence.studio.frame_selector import FrameSelector
from qoresence.studio.ghost_cut import (
    GhostEvent,
    cut_highlight,
    held_at,
    load_button_timeline,
    play_window,
    precursor_at,
)
from qoresence.studio.receipt import ReelReceipt, write_receipt
from qoresence.studio.reel_queue import ReelQueue, RenderJob, reset_reel_queue
from qoresence.studio.render_command import render_reels


@pytest.fixture(autouse=True)
def _reset_studio_queue():
    reset_reel_queue()
    yield
    reset_reel_queue()


def _write_clip(path: Path, frames: int = 30, fps: float = 10.0) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
    for i in range(frames):
        writer.write(np.full((240, 320, 3), 40 + (i % 20) * 8, dtype=np.uint8))
    writer.release()


def test_ghost_cut_writes_local_mp4(tmp_path):
    video_path = tmp_path / "hdmi_clip_cut.mp4"
    _write_clip(video_path)
    out = tmp_path / "reel_ghost.mp4"
    result = cut_highlight(
        video_path,
        {"kind": "confirm_chat", "label": "14-10 clutch", "t_s": 1.2},
        situation={"home_score": 14, "away_score": 10, "quarter": 4},
        output_path=out,
        pre_s=0.8,
        post_s=1.2,
        slow_last_s=0.4,
    )
    assert result.output_path.is_file()
    assert result.frames > 0
    rec = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert rec["renderer"] == "ghost_cut"
    assert rec["status"] == "completed"


def test_held_at_follows_press_release():
    tl = [
        GhostEvent(0.1, "cross", "press", 1.0),
        GhostEvent(0.4, "cross", "release", 0.0),
        GhostEvent(0.5, "r2", "trigger", 0.8),
        GhostEvent(0.9, "r2", "trigger", 0.0),
    ]
    assert "cross" in held_at(tl, 0.2)
    assert "cross" not in held_at(tl, 0.45)
    assert "r2" in held_at(tl, 0.6)
    assert "r2" not in held_at(tl, 1.0)


def test_precursor_at_window():
    tl = [
        GhostEvent(0.50, "r2", "press", 1.0, imu_precursor_ms=20.0),
        GhostEvent(0.80, "cross", "press", 1.0),
    ]
    names = {n for n, _ in precursor_at(tl, 0.49)}
    assert names == {"r2"}
    assert precursor_at(tl, 0.50) == []
    assert precursor_at(tl, 0.47) == []
    assert precursor_at(tl, 0.79) == []


def test_load_button_timeline_normalizes_clock(tmp_path):
    clip = tmp_path / "hdmi_clip_x.mp4"
    clip.write_bytes(b"x")
    side = tmp_path / "hdmi_clip_x.buttons.json"
    side.write_text(
        json.dumps(
            {
                "duration_s": 2.0,
                "events": [
                    {
                        "clock_ns": 1_000_000_000,
                        "kind": "press",
                        "name": "cross",
                        "value": 1,
                        "imu_precursor_ms": 18.0,
                    },
                    {"clock_ns": 1_200_000_000, "kind": "press", "name": "r2_btn", "value": 1},
                    {"clock_ns": 1_400_000_000, "kind": "release", "name": "cross", "value": 0},
                ],
            }
        ),
        encoding="utf-8",
    )
    tl = load_button_timeline(clip)
    assert len(tl) == 3
    assert tl[0].t_s == 0.0
    assert tl[0].imu_precursor_ms == 18.0
    assert tl[1].name == "r2"
    assert abs(tl[2].t_s - 0.4) < 0.001


def test_pick_play_chapter_skips_t0_chat():
    chapters = [
        {"kind": "confirm_chat", "t_s": 0.0, "label": "menu"},
        {"kind": "score_changed", "t_s": 8.2, "label": "TD", "coupling": 0.7},
        {"kind": "fast_chat", "t_s": 1.0, "label": "heat"},
    ]
    picked = pick_play_chapter(chapters, {"buttons_summary": {"cross": 12}})
    assert picked is not None
    assert picked["kind"] == "score_changed"
    assert score_play_chapter(chapters[0], {}) < score_play_chapter(chapters[1], {})


def test_pick_play_chapter_prefers_touchdown_label_over_t0_board():
    chapters = [
        {"kind": "confirm_chat", "t_s": 0.0, "label": "Live — board 7-7, Q1."},
        {
            "kind": "confirm_chat",
            "t_s": 10.038,
            "label": "TOUCHDOWN! Away storms back—14-13, and it's getting CLUTCH!",
        },
        {"kind": "input", "t_s": 25.5, "label": "input r2_btn"},
    ]
    picked = pick_play_chapter(
        chapters,
        {
            "button_onsets": [
                {"t_s": 0.0, "name": "r2", "kind": "press", "imu_precursor_ms": 78.0},
            ]
        },
    )
    assert picked is not None
    assert "TOUCHDOWN" in picked["label"]
    assert is_board_dump(chapters[0]) is True
    assert is_board_dump(chapters[1]) is False


def test_play_window_gives_td_room_for_the_throw():
    pre, post = play_window(
        {"kind": "confirm_chat", "label": "TOUCHDOWN! Away storms back—14-13", "t_s": 10.0}
    )
    assert pre >= 6.0
    assert post >= 12.0
    short = play_window({"kind": "fast_chat", "label": "heat", "t_s": 4.0})
    assert short[1] < post


def test_score_play_chapter_hid_near_boosts():
    ch = {"kind": "score_changed", "t_s": 8.2, "label": "TD"}
    bare = score_play_chapter(ch, {})
    bodied = score_play_chapter(
        ch,
        {
            "button_onsets": [
                {"t_s": 8.05, "name": "r2", "kind": "trigger", "imu_precursor_ms": 22.0},
            ]
        },
    )
    press_only = score_play_chapter(
        ch,
        {"button_onsets": [{"t_s": 8.05, "name": "r2", "kind": "trigger"}]},
    )
    far = score_play_chapter(
        ch,
        {"button_onsets": [{"t_s": 1.0, "name": "cross", "kind": "press"}]},
    )
    assert bodied > press_only > bare
    assert abs(far - bare) < 0.01
    hid_beats_chat = [
        {"kind": "confirm_chat", "t_s": 0.0, "label": "menu"},
        {"kind": "fast_chat", "t_s": 4.0, "label": "heat"},
    ]
    picked = pick_play_chapter(
        hid_beats_chat,
        {"button_onsets": [{"t_s": 3.85, "name": "r2", "kind": "press", "imu_precursor_ms": 16.0}]},
    )
    assert picked is not None
    assert picked["kind"] == "fast_chat"


def test_ghost_cut_receipt_records_binds(tmp_path):
    video_path = tmp_path / "hdmi_clip_bind.mp4"
    _write_clip(video_path, frames=24)
    side = tmp_path / "hdmi_clip_bind.buttons.json"
    side.write_text(
        json.dumps(
            {
                "events": [
                    {
                        "t_s": 1.05,
                        "kind": "press",
                        "name": "r2",
                        "value": 1,
                        "imu_precursor_ms": 18.0,
                    },
                    {"t_s": 1.40, "kind": "release", "name": "r2", "value": 0},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "reel_bind.mp4"
    result = cut_highlight(
        video_path,
        {"kind": "score_changed", "label": "TD", "t_s": 1.2},
        situation={"home_score": 14, "away_score": 10, "quarter": 4},
        output_path=out,
        pre_s=0.4,
        post_s=0.8,
        slow_last_s=0.2,
    )
    rec = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    binds = rec["metadata"]["binds"]
    assert binds
    assert binds[0]["mode"] == "TEMPORAL"
    assert binds[0]["hid_name"] == "r2"
    assert binds[0]["visual_kind"] == "score_changed"
    assert rec["metadata"]["imu_bodied"] is True


def test_frame_selector_extracts_png(tmp_path):
    video_path = tmp_path / "clip.mp4"
    _write_clip(video_path, frames=10)
    png = FrameSelector().extract_png(video_path, t_s=0.5, output_path=tmp_path / "frame.png")
    assert png is not None and png.is_file()
    img = cv2.imread(str(png))
    assert img is not None
    assert img.shape == (240, 320, 3)


def test_reel_queue_join_returns_when_jobs_finish(tmp_path):
    import time

    video_path = tmp_path / "hdmi_clip_join.mp4"
    _write_clip(video_path, frames=12)
    queue = ReelQueue(
        FrameSelector(),
        output_dir=tmp_path,
        jobs_file=tmp_path / "jobs.jsonl",
    )
    job = RenderJob(
        source_clip=str(video_path),
        chapter={"label": "TD", "kind": "touchdown", "t_s": 0.4},
        game_profile="ncaa_football_27",
    )
    started = time.monotonic()
    queue.submit([job])
    assert queue.join(timeout=10.0) is True
    assert time.monotonic() - started < 8.0
    updated = queue.get_job(job.job_id)
    assert updated is not None
    assert updated.status == "completed"


def test_reel_queue_processes_job(tmp_path):
    video_path = tmp_path / "hdmi_clip_test.mp4"
    _write_clip(video_path, frames=12)
    queue = ReelQueue(
        FrameSelector(),
        output_dir=tmp_path,
        jobs_file=tmp_path / "jobs.jsonl",
    )
    job = RenderJob(
        source_clip=str(video_path),
        chapter={"label": "TD", "kind": "touchdown", "t_s": 0.3},
        situation={"home_score": 21, "away_score": 7},
        game_profile="ncaa_football_27",
        session_id="test",
    )
    queue.submit([job])
    queue.join(timeout=10.0)
    updated = queue.get_job(job.job_id)
    assert updated is not None
    assert updated.status == "completed"
    assert Path(updated.output_path).is_file()


def test_receipt_round_trip(tmp_path):
    r = ReelReceipt(
        session_id="s",
        source_clip="clip.mp4",
        output_path=str(tmp_path / "reel.mp4"),
        status="completed",
        renderer="ghost_cut",
    )
    p = write_receipt(tmp_path / "reel.mp4", r)
    data = json.loads(p.read_text())
    assert data["renderer"] == "ghost_cut"
    assert data["status"] == "completed"


def test_render_reels_no_clips(tmp_path):
    config = RetinaUnifiedConfig(
        session_id="test",
        session_head_ns=1,
        studio=StudioConfig(enabled=True),
    )
    with pytest.raises((RuntimeError, FileNotFoundError)):
        render_reels(config, clip_path=str(tmp_path / "nope.mp4"), wait=False)


def test_studio_status_and_clip_sandbox(tmp_path):
    cfg = RetinaUnifiedConfig(
        session_id="test", session_head_ns=1, studio=StudioConfig(enabled=True)
    )
    payload = status_payload(cfg)
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["available"] is True
    assert payload["renderer"] == "ghost_cut"
    off = status_payload(RetinaUnifiedConfig(session_id="x", session_head_ns=1))
    assert off["enabled"] is False

    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "hdmi_clip_ok.mp4").write_bytes(b"x")
    resolved = resolve_clip_path("hdmi_clip_ok.mp4", clips_dir=clips)
    assert resolved is not None
    assert resolved.name == "hdmi_clip_ok.mp4"
    traversed = resolve_clip_path("..\\windows\\system.ini", clips_dir=clips)
    assert traversed is not None
    assert traversed.parent == clips.resolve()


def test_list_candidates_shape(monkeypatch):
    monkeypatch.setattr(
        "qoresence.foundry.index.get_render_candidates",
        lambda limit=3, kinds=None: [
            {
                "clip": "clips/hdmi_clip_demo.mp4",
                "chapter": {"kind": "score_changed", "t_s": 1.2, "label": "TD"},
                "score": 1.5,
                "buttons_summary": {},
                "graph_summary": None,
            }
        ],
    )
    items = list_candidates(limit=3)
    assert items[0]["clip_url"] == "/media/clips/hdmi_clip_demo.mp4"
    assert items[0]["chapter"]["kind"] == "score_changed"
    assert jobs_payload() == []


def test_foundry_bay_routes_registered():
    from qoresence.deck.server import _html, create_app

    html = _html("studio.html")
    if 'id="root"' in html or "id='root'" in html:
        assert "/assets/" in html
        app = create_app()
        if app is None:
            pytest.skip("fastapi not installed")
        paths = {getattr(route, "path", None) for route in app.routes}
        assert "/studio.html" in paths
        assert "/api/foundry/status" in paths
        return
    assert "Foundry Bay" in html
    assert "Cut highlight" in html
    deck = _html("deck.html")
    assert 'id="ctrlPlane"' in deck
    assert "WAITING FOR DUALSENSE" in deck
    assert 'id="feedDock"' in deck
    assert deck.find('id="feedDock"') < deck.find('id="rail"')
    lens = _html("overlay.html")
    assert 'id="pad"' in lens
    assert 'id="bind"' in lens
    assert 'id="body"' in lens
    app = create_app()
    if app is None:
        pytest.skip("fastapi not installed")
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/studio.html" in paths
    assert "/api/foundry/status" in paths


def test_foundry_status_route_uses_config():
    from qoresence.deck import server as deck_server

    app = deck_server.create_app()
    if app is None:
        pytest.skip("fastapi not installed")
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")
    cfg = RetinaUnifiedConfig(
        session_id="test", session_head_ns=1, studio=StudioConfig(enabled=True)
    )
    prev = deck_server._deck_config
    deck_server._deck_config = cfg
    try:
        client = TestClient(app)
        assert client.get("/studio.html").status_code == 200
        st = client.get("/api/foundry/status").json()
        assert st["enabled"] is True
        assert st["renderer"] == "ghost_cut"
    finally:
        deck_server._deck_config = prev


def test_studio_config_has_no_video_api():
    studio = StudioConfig()
    assert not hasattr(studio, "api_key")
    assert not hasattr(studio, "base_url")
    assert studio.enabled is False


def test_health_exposes_coupling():
    from qoresence.deck import server as deck_server

    app = deck_server.create_app()
    if app is None:
        pytest.skip("fastapi not installed")
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")
    client = TestClient(app)
    body = client.get("/health").json()
    assert body["ok"] is True
    assert "coupling" in body
    assert body["coupling"]["imu_bodied"] is False
    assert "binds" in body["coupling"]
