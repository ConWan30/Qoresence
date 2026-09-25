"""Stem card-audio track — clock-aligned WAV; silence for gaps; PCM never on the bus."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pytest

from qoresence.stem.audio import StemAudio
from qoresence.stem.audio_track import QUEUE_BLOCKS, StemAudioTrack, to_int16

S = 1_000_000_000
SR = 1000  # 1 sample == 1 ms keeps the arithmetic readable


def _block(n: int = 100, value: float = 0.5) -> np.ndarray:
    return np.full((n, 1), value, dtype=np.float32)


def _frames(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)


def _track(tmp_path: Path) -> StemAudioTrack:
    t = StemAudioTrack(tmp_path / "a.wav", start_ns=0, samplerate=SR)
    assert t.open()
    return t


def test_to_int16_clips_and_downmixes():
    out = to_int16(np.array([[2.0, 2.0], [-2.0, -2.0], [0.5, 0.5]], dtype=np.float32))
    assert out.dtype == np.int16
    assert out.tolist() == [32767, -32767, 16383]


def test_head_padded_so_sample_zero_is_start(tmp_path):
    t = _track(tmp_path)
    t.feed(int(0.6 * S), _block(100))  # block covers 0.5–0.6 s
    path = t.close()
    pcm = _frames(path)
    assert pcm.size == 600
    assert not pcm[:500].any()
    assert (pcm[500:] > 0).all()


def test_small_jitter_is_absorbed(tmp_path):
    t = _track(tmp_path)
    t.feed(int(0.1 * S), _block(100))
    t.feed(int(0.22 * S), _block(100))  # 20 ms late, inside tolerance
    t.close()
    st = t.stats()
    assert st["samples"] == 200
    assert st["silence_ms"] == 0.0 and st["trimmed_ms"] == 0.0


def test_dropout_filled_with_silence(tmp_path):
    t = _track(tmp_path)
    t.feed(int(0.1 * S), _block(100))
    t.feed(int(1.5 * S), _block(100))  # block covers 1.4–1.5 s
    path = t.close()
    pcm = _frames(path)
    assert pcm.size == 1500
    assert not pcm[100:1400].any()
    assert t.stats()["silence_ms"] == 1300.0


def test_ahead_of_clock_trims_block_head(tmp_path):
    t = _track(tmp_path)
    t.feed(int(0.1 * S), _block(100))
    t.feed(int(0.14 * S), _block(100))  # starts at 40 ms, 60 ms ahead of written
    t.close()
    st = t.stats()
    assert st["trimmed_ms"] == 60.0
    assert st["samples"] == 140


def test_close_pads_to_video_length(tmp_path):
    t = _track(tmp_path)
    t.feed(int(0.1 * S), _block(100))
    path = t.close(pad_to_s=2.0)
    assert _frames(path).size == 2000


def test_no_blocks_removes_file(tmp_path):
    t = _track(tmp_path)
    assert t.close(pad_to_s=2.0) is None
    assert not (tmp_path / "a.wav").exists()


def test_feed_is_drop_oldest_and_never_blocks(tmp_path):
    t = StemAudioTrack(tmp_path / "a.wav", start_ns=0, samplerate=SR)
    t0 = time.perf_counter()
    for i in range(QUEUE_BLOCKS + 10):
        t.feed(i, _block(1))
    assert (time.perf_counter() - t0) < 0.5
    assert t.stats()["dropped_blocks"] == 10


class _Bus:
    def __init__(self):
        self.payloads = []

    def emit_raw(self, **kw):
        self.payloads.append(kw["payload"])


def _armed_audio(bus=None) -> StemAudio:
    audio = StemAudio(bus)
    audio._device = (3, "USB3.0 Audio")
    audio._thread = threading.Thread(target=lambda: None)
    audio.samplerate = SR
    return audio


def test_capture_refused_without_card_device(tmp_path):
    audio = StemAudio(None)
    assert audio.start_capture(tmp_path / "x.wav", 0) is False
    assert audio.stop_capture(pad_to_s=1.0) is None


def test_on_block_taps_track_but_bus_gets_levels_only(tmp_path):
    bus = _Bus()
    audio = _armed_audio(bus)
    assert audio.start_capture(tmp_path / "s.wav", 0)
    assert audio.snapshot()["capturing"] is True
    audio._on_block(_block(100, 0.9), int(0.1 * S))
    path = audio.stop_capture(pad_to_s=0.5)
    assert path is not None and _frames(path).size == 500
    assert bus.payloads and all(set(p) == {"rms", "onset"} for p in bus.payloads)
    json.dumps(bus.payloads)
    assert audio.capture_stats()["blocks"] == 1
    assert audio.snapshot()["capturing"] is False


def _probe_durations(path: Path) -> dict[str, float]:
    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    return {s["codec_type"]: float(s["duration"]) for s in json.loads(out)["streams"]}


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not installed",
)
def test_stem_record_muxes_card_audio_end_to_end(tmp_path, monkeypatch):
    import cv2

    from qoresence.core.types import clock_ns
    from qoresence.stem.record import StemRecord
    from qoresence.vision import clip_buffer

    ok, jpg = cv2.imencode(".jpg", np.full((48, 64, 3), 90, dtype=np.uint8))
    assert ok
    seq = iter(range(1, 10**6))
    monkeypatch.setattr(clip_buffer, "get_latest_frame", lambda: (jpg.tobytes(), next(seq)))

    audio = _armed_audio()
    audio.samplerate = 48000
    rec = StemRecord(bus=None, out_dir=str(tmp_path), fps=10.0, audio=audio)
    rec.start()
    stop = threading.Event()

    def feeder():
        tone = np.sin(np.linspace(0, 2 * np.pi * 440 * 2048 / 48000, 2048)).astype(np.float32)
        while not stop.is_set():
            time.sleep(2048 / 48000)
            audio._on_block(tone * 0.3, clock_ns())

    th = threading.Thread(target=feeder, daemon=True)
    th.start()
    time.sleep(1.2)
    stop.set()
    th.join()
    rec.stop()

    snap = rec.snapshot()
    assert snap["h264"] is True and snap["audio"] is True
    final = Path(snap["path"])
    assert final.suffix == ".mp4" and final.is_file()
    assert not list(tmp_path.glob("*.wav"))
    durs = _probe_durations(final)
    assert "audio" in durs and "video" in durs
    assert abs(durs["audio"] - durs["video"]) <= 0.1


def test_stem_record_keeps_wav_when_audio_mux_fails(tmp_path, monkeypatch):
    import cv2

    from qoresence.stem.record import StemRecord
    from qoresence.vision import clip_buffer
    from qoresence.vision.clip_buffer import HdmiClipBuffer

    calls = []

    def fake_ffmpeg(src, dst, fps, audio_wav=None, *, timeout_s=120.0):
        calls.append(audio_wav)
        if audio_wav is not None:
            return False
        Path(dst).write_bytes(b"x" * 600)
        return True

    monkeypatch.setattr(HdmiClipBuffer, "_ffmpeg_h264", staticmethod(fake_ffmpeg))
    ok, jpg = cv2.imencode(".jpg", np.full((48, 64, 3), 90, dtype=np.uint8))
    seq = iter(range(1, 10**6))
    monkeypatch.setattr(clip_buffer, "get_latest_frame", lambda: (jpg.tobytes(), next(seq)))

    audio = _armed_audio()
    rec = StemRecord(bus=None, out_dir=str(tmp_path), fps=10.0, audio=audio)
    rec.start()
    audio._on_block(_block(100), rec._start_ns + int(0.1 * S))
    time.sleep(0.4)
    rec.stop()

    snap = rec.snapshot()
    assert calls[0] is not None and calls[1] is None
    assert snap["h264"] is True and snap["audio"] is False
    assert Path(snap["path"]).suffix == ".mp4"
    assert list(tmp_path.glob("*.wav"))


def test_runtime_stops_record_before_audio(monkeypatch):
    from qoresence.core.unified_config import StemConfig
    from qoresence.stem import runtime as runtime_mod

    order = []
    rt = runtime_mod.StemRuntime(StemConfig(audio=True, record=True), bus=None)
    assert rt.record is not None and rt.record.audio is rt.audio
    monkeypatch.setattr(rt.record, "stop", lambda: order.append("record"))
    monkeypatch.setattr(rt.audio, "stop", lambda: order.append("audio"))
    monkeypatch.setattr(rt.conductor, "stop", lambda: None)
    rt.stop()
    assert order == ["record", "audio"]
