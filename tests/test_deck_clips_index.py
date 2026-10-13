"""Deck clip listing: cached index, incremental by folder mtime, paginated."""

from __future__ import annotations

import os
import time
from pathlib import Path

from qoresence.deck.clips_index import ClipsIndex, find_reel


def _mk(root: Path, n: int, start: int = 0) -> None:
    for i in range(start, start + n):
        p = root / f"hdmi_clip_20261013_{i:06d}.mp4"
        p.write_bytes(b"x" * 10)
        os.utime(p, (1_700_000_000 + i, 1_700_000_000 + i))


def _old_list(root: Path) -> list[str]:
    from qoresence.vision.clip_excise import is_cut_render

    videos = [p for p in root.glob("hdmi_clip_*.mp4") if not is_cut_render(p)] + list(
        root.glob("hdmi_clip_*.avi")
    )
    videos.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return [p.name for p in videos[:40]]


def test_same_order_as_old_listing_and_skips_cut_renders(tmp_path):
    _mk(tmp_path, 60)
    (tmp_path / "hdmi_clip_20261013_000059.cut.mp4").write_bytes(b"c")
    (tmp_path / "other.mp4").write_bytes(b"o")
    idx = ClipsIndex(tmp_path)
    items, total = idx.items(0, 40)
    assert total == 60
    assert [i["name"] for i in items] == _old_list(tmp_path)


def test_rescans_only_when_folder_changes(tmp_path):
    _mk(tmp_path, 5)
    idx = ClipsIndex(tmp_path)
    idx.page()
    idx.page()
    idx.page()
    assert idx.scans == 1
    time.sleep(0.02)
    _mk(tmp_path, 1, start=99)
    st = os.stat(tmp_path)
    os.utime(tmp_path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000))
    page, total = idx.page()
    assert total == 6 and idx.scans == 2
    assert page[0].name.endswith("000099.mp4")


def test_pagination(tmp_path):
    _mk(tmp_path, 100)
    idx = ClipsIndex(tmp_path)
    p1, total = idx.page(0, 30)
    p2, _ = idx.page(30, 30)
    assert total == 100 and len(p1) == 30 and len(p2) == 30
    assert {c.name for c in p1}.isdisjoint({c.name for c in p2})
    assert idx.page(0, 10_000)[0].__len__() == 100  # limit capped at 200


def test_missing_folder_is_empty(tmp_path):
    idx = ClipsIndex(tmp_path / "nope")
    assert idx.items() == ([], 0)


def test_find_reel_cached(tmp_path):
    d = tmp_path / "x_cut"
    d.mkdir()
    (d / "reel_a.mp4").write_bytes(b"r")
    assert find_reel(tmp_path, "reel_a.mp4") == d / "reel_a.mp4"
    assert find_reel(tmp_path, "reel_missing.mp4") is None


def test_benchmark_3400_files(tmp_path):
    _mk(tmp_path, 3400)
    t0 = time.perf_counter()
    for _ in range(5):
        _old_list(tmp_path)
    old = (time.perf_counter() - t0) / 5
    idx = ClipsIndex(tmp_path)
    idx.items()  # first scan
    t0 = time.perf_counter()
    for _ in range(5):
        idx.items()
    new = (time.perf_counter() - t0) / 5
    print(f"3400 clips: old {old * 1e3:.1f} ms/request, cached {new * 1e3:.2f} ms/request")
    assert new < old / 5
