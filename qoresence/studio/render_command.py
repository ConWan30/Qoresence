"""High-level Ghost Cut orchestration."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from qoresence.core.unified_config import RetinaUnifiedConfig, StudioConfig, get_game_profile
from qoresence.foundry.index import FoundryIndex, pick_play_chapter

from .frame_selector import FrameSelector
from .receipt import now_ns
from .reel_queue import RenderJob, init_reel_queue

log = logging.getLogger(__name__)


def _resolve_config_studio(config: RetinaUnifiedConfig) -> StudioConfig | None:
    if not config.studio.enabled:
        return None
    return config.studio


def _situation_from_clip(clip_path: Path) -> dict[str, Any] | None:
    sidecar = clip_path.with_name(clip_path.stem + ".chapters.json")
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        why = data.get("why") or {}
        return {
            "home_score": why.get("home_score") or 0,
            "away_score": why.get("away_score") or 0,
            "quarter": why.get("quarter") or "",
            "possession": why.get("possession") or "",
            "clock_ns": 0,
        }
    except Exception:
        return None


def render_reels(
    config: RetinaUnifiedConfig,
    *,
    clip_path: str | Path | None = None,
    count: int | None = None,
    output_dir: str | Path | None = None,
    kinds: str | None = None,
    style: str | None = None,
    wait: bool = True,
    wait_timeout: float = 120.0,
) -> list[RenderJob]:
    """Queue local Ghost Cuts. ``style`` is ignored (kept for old callers)."""
    studio = _resolve_config_studio(config)
    if studio is None:
        raise RuntimeError("Studio not enabled. Set --studio or --foundry-reel")

    frame_selector = FrameSelector(cache_dir=output_dir or studio.output_dir)
    queue = init_reel_queue(
        frame_selector=frame_selector,
        output_dir=output_dir or studio.output_dir,
    )

    limit = count if count is not None else studio.max_reels_per_session
    candidates: list[dict[str, Any]] = []
    if clip_path:
        p = Path(clip_path)
        if not p.is_file():
            raise FileNotFoundError(clip_path)
        sidecar = p.with_name(p.stem + ".chapters.json")
        if not sidecar.is_file():
            raise FileNotFoundError(f"No chapters sidecar for {clip_path}")
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Bad chapters sidecar for {clip_path}") from exc
        chs = data.get("chapters") or []
        ch = pick_play_chapter(chs, data)
        if ch is None:
            raise RuntimeError(f"No usable play chapter in sidecar for {clip_path}")
        candidates = [
            {
                "clip": str(p.resolve()),
                "chapter": ch,
                "buttons_summary": data.get("buttons") if isinstance(data, dict) else {},
                "graph_summary": data.get("graph_summary") if isinstance(data, dict) else None,
            }
        ]
    else:
        candidates = FoundryIndex().get_render_candidates(limit=limit, kinds=kinds)

    jobs: list[RenderJob] = []
    for cand in candidates[:limit]:
        cp = Path(cand["clip"])
        if not cp.is_file():
            continue
        ch = cand.get("chapter") or {}
        situation = _situation_from_clip(cp) or {}
        gs = cand.get("graph_summary")
        if isinstance(gs, dict) and isinstance(gs.get("climax"), dict):
            situation["home_score"] = gs["climax"].get("home_score") or situation.get("home_score", 0)
            situation["away_score"] = gs["climax"].get("away_score") or situation.get("away_score", 0)

        game_profile = config.outcome.game_profile.value
        try:
            get_game_profile(game_profile)
        except Exception:
            game_profile = "ncaa_football_27"

        jobs.append(
            RenderJob(
                source_clip=str(cp.resolve()),
                chapter=ch,
                situation=situation,
                buttons_summary=cand.get("buttons_summary") or {},
                game_profile=game_profile,
                session_id=config.session_id,
                output_dir=str(output_dir) if output_dir else None,
                created_ns=now_ns(),
            )
        )

    if not jobs:
        return []

    queue.submit(jobs)
    log.info("Ghost Cut: queued %d highlight(s)", len(jobs))
    if wait:
        finished = queue.join(timeout=wait_timeout)
        if not finished:
            log.warning("Ghost Cut: timed out waiting for jobs")
        return [queue.get_job(j.job_id) for j in jobs if j.job_id]
    return jobs
