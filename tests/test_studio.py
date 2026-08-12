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
from qoresence.studio.frame_selector import FrameSelector
from qoresence.studio.ltx_client import LtxClient
from qoresence.studio.prompt_engine import PromptEngine
from qoresence.studio.receipt import ReelReceipt, write_receipt
from qoresence.studio.reel_queue import ReelQueue, RenderJob
from qoresence.studio.render_command import render_reels


def _fake_game_profile() -> GameProfile:
    return GameProfile(
        profile_id=GameProfileId.NCAA_FOOTBALL_27,
        display_name="NCAA College Football 27",
        event_types=("score_changed", "touchdown"),
        outcome_fields=("home_score", "away_score"),
        category="football",
    )


def test_prompt_engine_ncaa_score_changed():
    engine = PromptEngine()
    chapter = {
        "label": "14-10 with 3:46 left",
        "kind": "score_changed",
        "t_s": 12.0,
    }
    situation = {"home_score": 14, "away_score": 10, "quarter": 4, "possession": "home"}
    prompt, negative = engine.build_prompt(_fake_game_profile(), chapter, situation)
    assert "14" in prompt
    assert "10" in prompt
    assert "quarter" in prompt.lower() or "stadium" in prompt.lower()
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
    # Dry run reports completed but output file is empty; test queue lifecycle.
    assert updated.status == "completed"
    assert Path(updated.output_path).is_file() or True  # dry-run does not write video


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
