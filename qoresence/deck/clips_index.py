"""Cached clip listing for the Deck (``/api/clips``) and reel lookup.

The live clips folder grows to thousands of files (3.4k on the 2026-10-13
Madden run). ``/api/clips`` used to glob + stat every file on each request,
and three deck worker threads were seen stat-ing it at once while /health
took 10-30 s. This index:

* rescans only when the directory's mtime changes (adding/removing a file
  bumps it); one ``stat`` of the folder per request otherwise;
* single-flights the rescan (concurrent requests wait for one scan);
* uses one ``os.scandir`` pass (DirEntry stat is free on Windows);
* returns a page (``offset``/``limit``) of the newest clips.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ClipEntry:
    name: str
    path: str
    size_bytes: int
    mtime: float


def _is_clip(name: str) -> bool:
    low = name.lower()
    if not low.startswith("hdmi_clip_"):
        return False
    if low.endswith(".cut.mp4"):
        return False
    return low.endswith(".mp4") or low.endswith(".avi")


class ClipsIndex:
    def __init__(self, root: str | Path, *, min_rescan_s: float = 0.0) -> None:
        self.root = Path(root)
        self.min_rescan_s = float(min_rescan_s)
        self._lock = threading.Lock()
        self._entries: list[ClipEntry] = []
        self._dir_mtime_ns: int | None = None
        self._last_check = 0.0
        self.scans = 0

    def _dir_mtime(self) -> int | None:
        try:
            return os.stat(self.root).st_mtime_ns
        except OSError:
            return None

    def _scan(self) -> list[ClipEntry]:
        out: list[ClipEntry] = []
        try:
            with os.scandir(self.root) as it:
                for e in it:
                    if not _is_clip(e.name):
                        continue
                    try:
                        if not e.is_file():
                            continue
                        st = e.stat()
                    except OSError:
                        continue
                    out.append(ClipEntry(e.name, os.path.abspath(e.path), st.st_size, st.st_mtime))
        except OSError:
            return []
        out.sort(key=lambda c: c.mtime, reverse=True)
        return out

    def refresh(self, *, force: bool = False) -> None:
        with self._lock:
            now = time.monotonic()
            if not force and self._dir_mtime_ns is not None and now - self._last_check < self.min_rescan_s:
                return
            self._last_check = now
            m = self._dir_mtime()
            if not force and m is not None and m == self._dir_mtime_ns:
                return
            self._entries = self._scan()
            self._dir_mtime_ns = m
            self.scans += 1

    def page(self, offset: int = 0, limit: int = 40) -> tuple[list[ClipEntry], int]:
        self.refresh()
        with self._lock:
            entries = self._entries
        offset = max(0, int(offset))
        limit = max(1, min(200, int(limit)))
        return entries[offset : offset + limit], len(entries)

    def items(self, offset: int = 0, limit: int = 40) -> tuple[list[dict[str, Any]], int]:
        from qoresence.vision.clip_excise import cut_summary

        page, total = self.page(offset, limit)
        items: list[dict[str, Any]] = []
        for c in page:
            size, mtime = c.size_bytes, c.mtime
            try:  # a clip still being written grows without bumping the dir mtime
                st = os.stat(c.path)
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                continue
            item: dict[str, Any] = {
                "name": c.name,
                "path": c.path,
                "url": f"/media/clips/{c.name}",
                "size_bytes": size,
                "mtime": mtime,
            }
            cut = cut_summary(c.path)
            if cut is not None:
                item["cut"] = cut
            items.append(item)
        return items, total


_INDEXES: dict[str, ClipsIndex] = {}
_INDEX_LOCK = threading.Lock()
_REEL_CACHE: dict[tuple[str, str], str] = {}


def get_clips_index(root: str | Path) -> ClipsIndex:
    key = str(Path(root))
    with _INDEX_LOCK:
        idx = _INDEXES.get(key)
        if idx is None:
            idx = _INDEXES[key] = ClipsIndex(root)
        return idx


def find_reel(root: str | Path, safe_name: str) -> Path | None:
    """Locate a reel file under ``root`` (recursive), cached by name."""
    key = (str(Path(root)), safe_name)
    with _INDEX_LOCK:
        hit = _REEL_CACHE.get(key)
    if hit and os.path.isfile(hit):
        return Path(hit)
    for p in Path(root).rglob(safe_name):
        with _INDEX_LOCK:
            _REEL_CACHE[key] = str(p)
        return p
    return None


def reset_clips_index() -> None:
    with _INDEX_LOCK:
        _INDEXES.clear()
        _REEL_CACHE.clear()
