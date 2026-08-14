"""Deck-facing Foundry Bay helpers.

No event-bus emits. No lobe locks. Safe to call from the Deck HTTP thread
via ``asyncio.to_thread``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from qoresence.core.unified_config import RetinaUnifiedConfig
from qoresence.studio.frame_selector import FrameSelector
from qoresence.studio.reel_queue import RenderJob, get_reel_queue, init_reel_queue
from qoresence.studio.render_command import render_reels

log = logging.getLogger(__name__)

_CLIPS_DIR = Path("clips")


def resolve_clip_path(raw: str | None, clips_dir: str | Path = _CLIPS_DIR) -> Path | None:
    if not raw:
        return None
    root = Path(clips_dir).resolve()
    name = Path(str(raw)).name
    if not name:
        raise RuntimeError("clip name is empty")
    path = (root / name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("clip must be under clips/") from exc
    return path


def boot_studio(config: RetinaUnifiedConfig) -> dict[str, Any]:
    studio = getattr(config, "studio", None)
    if studio is None or not studio.enabled:
        return {"ok": False, "enabled": False}
    queue = init_reel_queue(
        frame_selector=FrameSelector(cache_dir=studio.output_dir),
        output_dir=studio.output_dir,
    )
    return {"ok": True, "enabled": True, "available": True, "jobs": len(queue.list_jobs(limit=50))}


def status_payload(config: RetinaUnifiedConfig | None) -> dict[str, Any]:
    studio = getattr(config, "studio", None) if config is not None else None
    enabled = bool(studio and studio.enabled)
    queue = get_reel_queue()
    jobs = queue.list_jobs(limit=50) if queue is not None else []
    return {
        "ok": True,
        "enabled": enabled,
        "available": enabled,
        "renderer": "ghost_cut",
        "max_reels": studio.max_reels_per_session if studio else 3,
        "job_count": len(jobs),
        "processing": sum(1 for j in jobs if j.status == "processing"),
        "completed": sum(1 for j in jobs if j.status == "completed"),
        "failed": sum(1 for j in jobs if j.status == "failed"),
    }


def list_candidates(limit: int = 8, kinds: str | None = None) -> list[dict[str, Any]]:
    from qoresence.foundry.index import get_render_candidates

    raw = get_render_candidates(limit=limit, kinds=kinds)
    out: list[dict[str, Any]] = []
    for item in raw:
        clip = str(item.get("clip") or "")
        name = Path(clip).name if clip else ""
        out.append(
            {
                "clip": clip,
                "name": name,
                "clip_url": f"/media/clips/{name}" if name else "",
                "buttons_url": f"/media/clips/{Path(name).stem}.buttons.json" if name else "",
                "chapter": item.get("chapter") or {},
                "score": item.get("score"),
                "buttons_summary": item.get("buttons_summary") or {},
                "graph_summary": item.get("graph_summary"),
                "hid_near": item.get("hid_near", 0),
                "bodied_onsets": item.get("bodied_onsets", 0),
                "onset_count": item.get("onset_count", 0),
            }
        )
    return out


def queue_renders(
    config: RetinaUnifiedConfig,
    *,
    clip: str | None = None,
    count: int | None = None,
    kinds: str | None = None,
    style: str | None = None,
) -> list[RenderJob]:
    studio = getattr(config, "studio", None)
    if studio is None or not studio.enabled:
        raise RuntimeError("studio not enabled — start Deck with --studio or --foundry-reel")
    cap = max(1, int(studio.max_reels_per_session or 3))
    limit = min(max(1, int(count or cap)), cap)
    clip_path = resolve_clip_path(clip) if clip else None
    if clip and clip_path is not None and not clip_path.is_file():
        raise FileNotFoundError(f"clip not found: {clip_path.name}")
    return render_reels(config, clip_path=clip_path, count=limit, kinds=kinds, wait=False)


def jobs_payload(limit: int = 50) -> list[dict[str, Any]]:
    queue = get_reel_queue()
    if queue is None:
        return []
    return [j.to_dict() for j in queue.list_jobs(limit=limit)]
