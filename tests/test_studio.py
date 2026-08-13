"""Tests for Qoresence Studio / Foundry Reels."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from qoresence.core.unified_config import (
    GameProfile,
    GameProfileId,
    RetinaUnifiedConfig,
    StudioConfig,
)
from qoresence.studio.api import jobs_payload, list_candidates, resolve_clip_path, status_payload
from qoresence.studio.frame_selector import FrameSelector
from qoresence.studio.ltx_client import (
    LtxClient,
    _resolve_api_key,
    normalize_duration,
)
from qoresence.studio.prompt_engine import STYLE_LOCK, PromptEngine
from qoresence.studio.receipt import ReelReceipt, write_receipt
from qoresence.studio.reel_queue import ReelQueue, RenderJob, reset_reel_queue
from qoresence.studio.render_command import render_reels


@pytest.fixture(autouse=True)
def _reset_studio_queue():
    reset_reel_queue()
    yield
    reset_reel_queue()


def _fake_game_profile() -> GameProfile:
    return GameProfile(
        profile_id=GameProfileId.NCAA_FOOTBALL_27,
        display_name="NCAA College Football 27",
        event_types=("score_changed", "touchdown"),
        outcome_fields=("home_score", "away_score"),
        category="football",
    )


def test_ghost_cut_writes_local_mp4(tmp_path):
    from qoresence.studio.ghost_cut import cut_highlight

    video_path = tmp_path / "hdmi_clip_cut.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 240))
    for i in range(30):
        writer.write(np.full((240, 320, 3), 40 + i * 4, dtype=np.uint8))
    writer.release()
    out = tmp_path / "reel_ghost.mp4"
    result = cut_highlight(
        video_path,
        {"kind": "confirm_chat", "label": "14-10 clutch", "t_s": 1.2},
        situation={"home_score": 14, "away_score": 10, "quarter": 4},
        buttons_summary={"cross": 3, "r1": 1},
        output_path=out,
        pre_s=0.8,
        post_s=1.2,
        slow_last_s=0.4,
    )
    assert result.output_path.is_file()
    assert result.frames > 0
    assert result.receipt_path.is_file()
    rec = json.loads(result.receipt_path.read_text(encoding="utf-8"))
    assert rec["metadata"]["renderer"] == "ghost_cut"
    assert rec["status"] == "completed"


def test_prompt_engine_ncaa_score_changed():
    engine = PromptEngine()
    chapter = {
        "label": "14-10 with 3:46 left",
        "kind": "score_changed",
        "t_s": 12.0,
    }
    situation = {"home_score": 14, "away_score": 10, "quarter": 4, "possession": "home"}
    prompt, negative = engine.build_prompt(_fake_game_profile(), chapter, situation)
    assert prompt.startswith(STYLE_LOCK)
    assert "14" in prompt
    assert "10" in prompt
    assert "quarter" in prompt.lower() or "stadium" in prompt.lower()
    assert "sports broadcast" not in prompt.lower()
    assert "football players as football players" in prompt.lower()
    assert "matching the source frame" in prompt.lower()
    assert "no character redesign" in prompt.lower()
    assert "Avatar-film CG characters" not in prompt
    assert "luminous oversized eyes" not in prompt.lower()
    assert "live-action" in negative
    assert "character redesign" in negative
    assert negative


def test_prompt_engine_payload():
    engine = PromptEngine()
    payload = engine.build_payload(
        _fake_game_profile(),
        {"label": "TD!", "kind": "touchdown", "t_s": 8.0},
        situation={"home_score": 21, "away_score": 7},
        duration=6,
    )
    assert payload.prompt
    assert payload.model == "ltx-2-3-pro"
    assert payload.duration == 6
    assert payload.resolution == "1920x1080"


def test_frame_selector_extracts_png(tmp_path):
    # Create a tiny synthetic MP4.
    video_path = tmp_path / "clip.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(video_path), fourcc, 10.0, (320, 240))
    assert writer.isOpened()
    for i in range(10):
        frame = np.full((240, 320, 3), i * 25, dtype=np.uint8)
        writer.write(frame)
    writer.release()

    selector = FrameSelector()
    png = selector.extract_png(video_path, t_s=0.5, output_path=tmp_path / "frame.png")
    assert png is not None
    assert png.is_file()
    img = cv2.imread(str(png))
    assert img is not None
    assert img.shape == (240, 320, 3)


def test_ltx_client_dry_run():
    client = LtxClient(api_key="fake", dry_run=True)
    job = client.submit_image_to_video("https://example.com/img.png", "prompt")
    assert job.job_id == "dry-run"
    assert job.status == "completed"


def test_ltx_client_upload_and_submit(monkeypatch, tmp_path):
    import requests

    client = LtxClient(api_key="fake")
    png = tmp_path / "frame.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")

    calls = []

    def fake_request(method, url, **kw):
        calls.append((method, url))
        resp = MagicMock()
        if method == "POST" and "/v1/upload" in url:
            resp.status_code = 200
            resp.headers = {"Content-Type": "application/json"}
            resp.text = '{"upload_url":"https://storage.example.com/up","storage_uri":"https://storage.example.com/img.png"}'
            resp.json.return_value = {
                "upload_url": "https://storage.example.com/up",
                "storage_uri": "https://storage.example.com/img.png",
            }
            return resp
        if method == "PUT" and "storage.example.com/up" in url:
            resp.status_code = 200
            resp.headers = {"Content-Type": "application/json"}
            resp.json.return_value = {}
            resp.text = ""
            return resp
        if method == "POST" and "/v2/image-to-video" in url:
            resp.status_code = 202
            resp.headers = {"Content-Type": "application/json"}
            resp.json.return_value = {"id": "job-123", "status": "pending"}
            resp.text = '{"id":"job-123","status":"pending"}'
            return resp
        resp.status_code = 404
        resp.text = ""
        resp.json.return_value = {}
        return resp

    monkeypatch.setattr(requests, "request", fake_request)
    storage_uri = client.upload_image(png)
    assert storage_uri == "https://storage.example.com/img.png"
    job = client.submit_image_to_video(storage_uri, "prompt")
    assert job.job_id == "job-123"


def test_reel_queue_join_returns_when_jobs_finish(tmp_path):
    import time

    video_path = tmp_path / "hdmi_clip_join.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 240))
    for _i in range(5):
        writer.write(np.full((240, 320, 3), 128, dtype=np.uint8))
    writer.release()
    queue = ReelQueue(
        LtxClient(api_key="fake", dry_run=True),
        PromptEngine(),
        FrameSelector(),
        output_dir=tmp_path,
        jobs_file=tmp_path / "jobs.jsonl",
    )
    job = RenderJob(
        source_clip=str(video_path),
        chapter={"label": "TD", "kind": "touchdown", "t_s": 0.1},
        game_profile="ncaa_football_27",
        duration=6,
    )
    started = time.monotonic()
    queue.submit([job])
    assert queue.join(timeout=10.0) is True
    assert time.monotonic() - started < 8.0
    updated = queue.get_job(job.job_id)
    assert updated is not None
    assert updated.status == "completed"


def test_reel_queue_processes_job(monkeypatch, tmp_path):
    import cv2

    # Synthetic clip.
    video_path = tmp_path / "hdmi_clip_test.mp4"
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (320, 240))
    for _i in range(5):
        writer.write(np.full((240, 320, 3), 128, dtype=np.uint8))
    writer.release()

    # Fake LTX client that completes instantly.
    client = LtxClient(api_key="fake", dry_run=True)
    engine = PromptEngine()
    selector = FrameSelector()
    queue = ReelQueue(client, engine, selector, output_dir=tmp_path, jobs_file=tmp_path / "jobs.jsonl")

    job = RenderJob(
        source_clip=str(video_path),
        chapter={"label": "TD", "kind": "touchdown", "t_s": 0.1},
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
        ltx_prompt="prompt",
        ltx_job_id="j",
        output_path=str(tmp_path / "reel.mp4"),
        status="completed",
    )
    p = write_receipt(tmp_path / "reel.mp4", r)
    assert p.is_file()
    data = json.loads(p.read_text())
    assert data["ltx_job_id"] == "j"
    assert data["status"] == "completed"


def test_render_reels_no_clips(tmp_path):
    config = RetinaUnifiedConfig(
        session_id="test",
        session_head_ns=1,
        studio=StudioConfig(enabled=True, api_key="fake", dry_run=True),
    )
    with pytest.raises((RuntimeError, FileNotFoundError)):
        render_reels(config, clip_path=str(tmp_path / "nope.mp4"), wait=False)


def test_resolve_api_key_strips_label_and_quotes(tmp_path):
    assert _resolve_api_key("LTX: ltxv_abc123") == "ltxv_abc123"
    assert _resolve_api_key('API KEY: "ltxv_quoted"') == "ltxv_quoted"
    key_file = tmp_path / "ltx.key"
    key_file.write_text("LTX: ltxv_from_file\n# comment\n", encoding="utf-8")
    assert _resolve_api_key(api_key_file=str(key_file)) == "ltxv_from_file"


def test_normalize_duration_snaps_invalid_pro_values():
    assert normalize_duration(5, "ltx-2-3-pro") == 6
    assert normalize_duration(6, "ltx-2-3-pro") == 6
    assert normalize_duration(9, "ltx-2-3-pro") == 8
    assert normalize_duration(20, "ltx-2-3-fast") == 20
    assert StudioConfig().duration == 6


def test_ltx_upload_forwards_required_headers_and_empty_2xx(monkeypatch, tmp_path):
    import requests

    client = LtxClient(api_key="ltxv_secret")
    png = tmp_path / "frame.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n")
    seen = {}

    def fake_request(method, url, **kw):
        resp = MagicMock()
        resp.content = b""
        resp.text = ""
        resp.json.side_effect = ValueError("no json")
        if method == "POST" and "/v1/upload" in url:
            resp.status_code = 200
            resp.headers = {"Content-Type": "application/json"}
            payload = {
                "upload_url": "https://storage.googleapis.com/bucket/up",
                "storage_uri": "ltx://ltxv-api-prd/uploads/x",
                "required_headers": {"x-goog-content-length-range": "0,10485760"},
            }
            resp.text = json.dumps(payload)
            resp.json.side_effect = None
            resp.json.return_value = payload
            return resp
        if method == "PUT" and "storage.googleapis.com" in url:
            seen["put_headers"] = dict(kw.get("headers") or {})
            resp.status_code = 200
            resp.headers = {"Content-Type": "application/xml"}
            resp.content = b""
            resp.text = ""
            return resp
        resp.status_code = 404
        resp.headers = {}
        return resp

    monkeypatch.setattr(requests, "request", fake_request)
    uri = client.upload_image(png)
    assert uri == "ltx://ltxv-api-prd/uploads/x"
    assert seen["put_headers"]["x-goog-content-length-range"] == "0,10485760"
    assert "Authorization" not in seen["put_headers"]


def test_ltx_submit_omits_aspect_ratio_and_snaps_duration(monkeypatch):
    import requests

    client = LtxClient(api_key="ltxv_secret")
    captured = {}

    def fake_request(method, url, **kw):
        captured["json"] = kw.get("json")
        resp = MagicMock()
        resp.status_code = 202
        resp.headers = {"Content-Type": "application/json"}
        resp.content = b'{"id":"job-1","status":"pending"}'
        resp.text = '{"id":"job-1","status":"pending"}'
        resp.json.return_value = {"id": "job-1", "status": "pending"}
        return resp

    monkeypatch.setattr(requests, "request", fake_request)
    job = client.submit_image_to_video("ltx://x", "prompt", duration=5, aspect_ratio="16:9")
    assert job.job_id == "job-1"
    assert captured["json"]["duration"] == 6
    assert "aspect_ratio" not in captured["json"]


def test_ltx_download_does_not_send_auth(monkeypatch, tmp_path):
    import requests

    client = LtxClient(api_key="ltxv_secret")
    seen = {}

    def fake_request(method, url, **kw):
        seen["headers"] = dict(kw.get("headers") or {})
        seen["url"] = url
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"Content-Type": "video/mp4"}
        resp.content = b"\x00\x00mp4"
        resp.text = ""
        resp.json.side_effect = ValueError("not json")
        return resp

    monkeypatch.setattr(requests, "request", fake_request)
    out = tmp_path / "reel.mp4"
    client.download_video("https://storage.googleapis.com/bucket/video.mp4", out)
    assert out.read_bytes() == b"\x00\x00mp4"
    assert "Authorization" not in seen["headers"]
    assert seen["url"].startswith("https://storage.googleapis.com/")


def test_studio_status_and_clip_sandbox(tmp_path):
    cfg = RetinaUnifiedConfig(
        session_id="test",
        session_head_ns=1,
        studio=StudioConfig(enabled=True, api_key="fake", dry_run=True, duration=5),
    )
    payload = status_payload(cfg)
    assert payload["ok"] is True
    assert payload["enabled"] is True
    assert payload["available"] is True
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


def test_prompt_engine_default_duration_and_templates():
    engine = PromptEngine()
    payload = engine.build_payload(
        _fake_game_profile(),
        {"label": "TD", "kind": "touchdown", "t_s": 1.0},
    )
    assert payload.duration == 6
    assert payload.model == "ltx-2-3-pro"
    assert engine.template_dir is not None
    assert engine.template_dir.name == "prompts"


def test_foundry_bay_routes_registered():
    from qoresence.deck.server import _html, create_app

    html = _html("studio.html")
    assert "Foundry Bay" in html
    assert "/api/foundry/status" in html
    assert "Cut highlight" in html
    app = create_app()
    if app is None:
        pytest.skip("fastapi not installed")
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/studio.html" in paths
    assert "/api/foundry/status" in paths
    assert "/api/foundry/candidates" in paths


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
        session_id="test",
        session_head_ns=1,
        studio=StudioConfig(enabled=True, api_key="fake", dry_run=True),
    )
    prev = deck_server._deck_config
    deck_server._deck_config = cfg
    try:
        client = TestClient(app)
        page = client.get("/studio.html")
        assert page.status_code == 200
        assert "Foundry Bay" in page.text
        st = client.get("/api/foundry/status").json()
        assert st["ok"] is True
        assert st["enabled"] is True
        jobs = client.get("/api/foundry/jobs").json()
        assert jobs["ok"] is True
        assert jobs["jobs"] == []
    finally:
        deck_server._deck_config = prev
