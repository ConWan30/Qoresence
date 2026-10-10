"""Model download is opt-in; the person guard fails closed without the model."""

from __future__ import annotations

import logging
import sys
import types
import urllib.request

import numpy as np
import pytest

from qoresence.lobes import streamer
from qoresence.vision import motion_tracker as mt
from qoresence.vision.motion_tracker import ModelDownloadNotAllowed, MotionTracker


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(mt.ALLOW_MODEL_DOWNLOAD_ENV, raising=False)

    def _boom(*a, **k):
        raise AssertionError("network used")

    monkeypatch.setattr(urllib.request, "urlretrieve", _boom)


def test_missing_model_no_opt_in_raises_without_network():
    with pytest.raises(ModelDownloadNotAllowed) as ei:
        MotionTracker._ensure_mediapipe_model()
    assert mt.ALLOW_MODEL_DOWNLOAD_ENV in str(ei.value)
    assert "models" in str(ei.value)


@pytest.mark.parametrize("val", ["0", "", "true", "yes"])
def test_only_exact_one_opts_in(monkeypatch, val):
    monkeypatch.setenv(mt.ALLOW_MODEL_DOWNLOAD_ENV, val)
    with pytest.raises(ModelDownloadNotAllowed):
        MotionTracker._ensure_mediapipe_model()


def test_existing_model_used_without_opt_in(tmp_path):
    (tmp_path / "models").mkdir()
    (tmp_path / "models" / mt.MODEL_FILENAME).write_bytes(b"x")
    assert MotionTracker._ensure_mediapipe_model().endswith(mt.MODEL_FILENAME)


def test_opt_in_downloads_via_mocked_urlretrieve(monkeypatch, tmp_path):
    monkeypatch.setenv(mt.ALLOW_MODEL_DOWNLOAD_ENV, "1")
    calls = []

    def fake(url, dest):
        calls.append(url)
        open(dest, "wb").write(b"m")

    monkeypatch.setattr(urllib.request, "urlretrieve", fake)
    path = MotionTracker._ensure_mediapipe_model()
    assert calls == [mt.MODEL_URL]
    assert (tmp_path / path).exists()


def test_person_guard_fails_closed_and_logs_hint(monkeypatch, caplog):
    # Provide fake mediapipe modules so the code reaches the model lookup.
    names = [
        "mediapipe",
        "mediapipe.tasks",
        "mediapipe.tasks.python",
        "mediapipe.tasks.python.core",
        "mediapipe.tasks.python.core.base_options",
        "mediapipe.tasks.python.vision",
        "mediapipe.tasks.python.vision.core",
        "mediapipe.tasks.python.vision.core.vision_task_running_mode",
        "mediapipe.tasks.python.vision.object_detector",
    ]
    for n in names:
        m = types.ModuleType(n)
        m.BaseOptions = object
        m.VisionTaskRunningMode = types.SimpleNamespace(IMAGE=0)
        m.ObjectDetector = object
        m.ObjectDetectorOptions = object
        monkeypatch.setitem(sys.modules, n, m)
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    with caplog.at_level(logging.ERROR):
        assert streamer._frame_contains_person(frame) is True
    text = caplog.text
    assert "NOT cleared" in text and mt.ALLOW_MODEL_DOWNLOAD_ENV in text


def test_person_guard_without_mediapipe_still_fails_closed(monkeypatch):
    monkeypatch.setitem(sys.modules, "mediapipe", None)
    assert streamer._frame_contains_person(np.zeros((4, 4, 3), np.uint8)) is True
