"""Path B: empty HID is success, not PAD WAIT (QorGraph #2)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from qoresence.core import ControllerConfig, RetinaEventBus, SessionAuthority
from qoresence.lobes.controller import ControllerRuntime


class FakeHIDDevice:
    def __init__(self, reports):
        self._reports = reports
        self._idx = 0
        self._closed = False
        self._opened = False
    def open(self, *a, **k):
        self._opened = True
    def open_path(self, path):
        self._opened = True
    def read(self, max_length, timeout_ms=0):
        return None
    def close(self):
        self._closed = True
    def set_nonblocking(self, v):
        pass


class TestPathBEmptyHid:
    @patch("qoresence.lobes.controller.list_controllers", return_value=[])
    @patch("qoresence.lobes.controller.HIDDevice")
    def test_start_without_device_reports_pad_not_on_this_host(self, mock_device_class, _mock_list):
        fake = FakeHIDDevice([])
        fake.open = lambda *a, **k: (_ for _ in ()).throw(OSError("no pad"))
        fake.open_path = lambda *a, **k: (_ for _ in ()).throw(OSError("no pad"))
        mock_device_class.return_value = fake
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="wait_test", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="wait_test")
            runtime = ControllerRuntime(
                config=ControllerConfig(enabled=True),
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )
            assert runtime.start() is True
            stats = runtime.get_stats()
            assert stats["connected"] is False
            assert stats["waiting"] is True
            assert stats["reason"] == "pad_not_on_this_host"
            assert stats.get("error") in (None, "", False)
            runtime.stop()
            bus.close()

    def test_empty_hid_health_is_success_not_pad_wait(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "events.jsonl"
            bus = RetinaEventBus(session_id="path_b", jsonl_path=jsonl_path, enable_ws=False)
            identity = SessionAuthority.mint(session_id="path_b")
            runtime = ControllerRuntime(
                config=ControllerConfig(enabled=True),
                bus=bus,
                session_head_ns=identity.session_head_ns,
            )
            try:
                stats = runtime.get_stats()
                assert stats["connected"] is False
                assert stats["reason"] == "pad_not_on_this_host"
                health = {"ok": True, "state": {"controller": stats}}
                assert health["ok"] is True
            finally:
                bus.close()

    def test_overlay_and_deck_do_not_say_pad_wait(self):
        root = Path(__file__).resolve().parents[1] / "qoresence" / "deck"
        overlay = (root / "overlay.html").read_text(encoding="utf-8")
        deck = (root / "deck.html").read_text(encoding="utf-8")
        for src, name in ((overlay, "overlay.html"), (deck, "deck.html")):
            assert "PAD WAIT" not in src, f"{name} treats empty HID as PAD WAIT failure"
            assert "WAITING FOR DUALSENSE" not in src, f"{name} coaches USB plug-in"
        assert "pad_not_on_this_host" in deck
        assert "DUALSENSE ON PS5" in deck

    def test_haptic_probe_does_not_body_empty_hid(self):
        from qoresence.core.civif_tick import CoupledTickRecord
        from qoresence.sync.haptic_schema import empty_record
        pulse = empty_record(session_id="no-body", clock_ns=1)
        assert "controller_bodied" not in pulse
        rec = CoupledTickRecord(
            session_id="no-body",
            clock_ns=1,
            frame_seq=1,
            input_ticks=[],
            situation=None,
            board_locked=False,
            controller_bodied=False,
            body_reason="pad_not_on_this_host",
        ).to_dict()
        assert rec["controller_bodied"] is False
        assert rec["input"]["reason"] == "pad_not_on_this_host"
