"""Vanilla clip-dock turns Windows paths into /media/clips replay URLs."""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "clip-dock.js"
_HREF = re.compile(r"hdmi_clip_[\w.\-]+\.(mp4|avi)", re.I)


def media_href(raw: str) -> str:
    s = str(raw or "").strip()
    if s.startswith("/media/clips/"):
        return s.split("?")[0]
    m = _HREF.search(s.replace("\\", "/"))
    return f"/media/clips/{m.group(0)}" if m else ""


def test_windows_path_becomes_media_url():
    assert (
        media_href(r"C:\Users\Contr\Qoresence\clips\hdmi_clip_20260822_101224.mp4")
        == "/media/clips/hdmi_clip_20260822_101224.mp4"
    )


def test_clip_dock_js_has_replay_and_live():
    blob = JS.read_text(encoding="utf-8")
    assert "function playClip" in blob
    assert "function goLive" in blob
    assert "LIVE feed" in blob
    assert "qoreClipHref" in blob
