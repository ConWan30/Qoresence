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
from qoresence.studio.ltx_client import LtxClient
from qoresence.studio.prompt_engine import PromptEngine
from qoresence.studio.reel_queue import RenderJob, get_reel_queue, init_reel_queue
from qoresence.studio.render_command import render_reels

log = logging.getLogger(__name__)

_CLIPS_DIR = Path("clips")


def resolve_clip_path(raw: str | None, clips_dir: str | Path = _CLIPS_DIR) -> Path | None:
    """Accept a filename or path and resolve it under the clips directory."""
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
    """Create the process-wide reel queue if Studio is enabled."""
    studio = getattr(config, "studio", None)
    if studio is None or not studio.enabled:
        return {"ok": False, "enabled": False}
    client = LtxClient(
        api_key=studio.api_key,
        api_key_file=studio.api_key_file,
        base_url=studio.base_url,
        endpoint=studio.endpoint,
        timeout_s=studio.timeout_s,
        poll_interval_s=studio.poll_interval_s,
        max_poll_s=studio.max_poll_s,
        dry_run=studio.dry_run,
    )
    queue = init_reel_queue(
        client,
        PromptEngine(),
        frame_selector=FrameSelector(cache_dir=studio.output_dir),
        output_dir=studio.output_dir,
    )
    return {
        "ok": True,
        "enabled": True,
        "available": client.is_available(),
        "jobs": len(queue.list_jobs(limit=50)),
    }


def status_payload(config: RetinaUnifiedConfig | None) -> dict[str, Any]:
    studio = getattr(config, "studio", None) if config is not None else None
    enabled = bool(studio and studio.enabled)
    client_available = False
    if enabled and studio is not None:
        client_available = LtxClient(
            api_key=studio.api_key,
            api_key_file=studio.api_key_file,
            dry_run=studio.dry_run,
        ).is_available()
    queue = get_reel_queue()
    jobs = queue.list_jobs(limit=50) if queue is not None else []
    return {
        "ok": True,
        "enabled": enabled,
        "available": client_available,
        "dry_run": bool(studio.dry_run) if studio else False,
        "model": studio.model if studio else "ltx-2-3-pro",
        "duration": studio.duration if studio else 6,
        "resolution": studio.resolution if studio else "1920x1080",
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
        chapter = item.get("chapter") or {}
        out.append(
            {
                "clip": clip,
                "name": name,
                "clip_url": f"/media/clips/{name}" if name else "",
                "chapter": chapter,
                "score": item.get("score"),
                "buttons_summary": item.get("buttons_summary") or {},
                "graph_summary": item.get("graph_summary"),
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
    return render_reels(
        config,
        clip_path=clip_path,
        count=limit,
        kinds=kinds,
        style=style,
        wait=False,
    )


def jobs_payload(limit: int = 50) -> list[dict[str, Any]]:
    queue = get_reel_queue()
    if queue is None:
        return []
    return [j.to_dict() for j in queue.list_jobs(limit=limit)]
