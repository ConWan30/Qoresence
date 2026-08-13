"""High-level `qoresence render-reels` orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from qoresence.core.unified_config import RetinaUnifiedConfig, StudioConfig, get_game_profile
from qoresence.foundry.index import FoundryIndex

from .frame_selector import FrameSelector
from .ltx_client import LtxClient, normalize_duration
from .prompt_engine import PromptEngine
from .receipt import now_ns
from .reel_queue import RenderJob, init_reel_queue

log = logging.getLogger(__name__)


def _resolve_config_studio(config: RetinaUnifiedConfig) -> StudioConfig | None:
    if not config.studio.enabled:
        return None
    return config.studio


def _situation_from_clip(clip_path: Path, clip_dir: Path) -> dict[str, Any] | None:
    """Best-effort load of chapter/situation context from sidecars."""
    sidecar = clip_path.with_name(clip_path.stem + ".chapters.json")
    if not sidecar.is_file():
        return None
    try:
        import json

        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return {
            "home_score": (data.get("why") or {}).get("home_score") or 0,
            "away_score": (data.get("why") or {}).get("away_score") or 0,
            "quarter": (data.get("why") or {}).get("quarter") or "",
            "possession": (data.get("why") or {}).get("possession") or "",
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
    wait_timeout: float = 600.0,
) -> list[RenderJob]:
    """Queue and optionally wait for LTX reels from Foundry clips.

    Returns the list of RenderJobs submitted.
    """
    studio = _resolve_config_studio(config)
    if studio is None:
        raise RuntimeError("Studio not enabled. Set --foundry-reel or QORESENCE_STUDIO_ENABLED=1")

    client = LtxClient(
        api_key=studio.api_key,
        api_key_file=studio.api_key_file,
        base_url=studio.base_url,
        endpoint=studio.endpoint,
        timeout_s=studio.timeout_s,
        poll_interval_s=studio.poll_interval_s,
        max_poll_s=studio.max_poll_s,
        dry_run=True,
    )
    prompt_engine = PromptEngine()
    frame_selector = FrameSelector(cache_dir=output_dir or studio.output_dir)
    queue = init_reel_queue(
        client,
        prompt_engine,
        frame_selector=frame_selector,
        output_dir=output_dir or studio.output_dir,
    )
    render_duration = normalize_duration(studio.duration, studio.model)

    # Collect candidates.
    limit = count if count is not None else studio.max_reels_per_session
    candidates: list[dict[str, Any]] = []
    if clip_path:
        p = Path(clip_path)
        if not p.is_file():
            raise FileNotFoundError(clip_path)
        sidecar = p.with_name(p.stem + ".chapters.json")
        if not sidecar.is_file():
            raise FileNotFoundError(f"No chapters sidecar for {clip_path}")
        ch = None
        try:
            import json

            data = json.loads(sidecar.read_text(encoding="utf-8"))
            chs = data.get("chapters") or []
            ch = chs[0] if chs else None
        except Exception:
            pass
        if ch is None:
            raise RuntimeError(f"No chapters in sidecar for {clip_path}")
        candidates = [
            {
                "clip": str(p.resolve()),
                "chapter": ch,
                "buttons_summary": data.get("buttons") if isinstance(data, dict) else {},
                "graph_summary": data.get("graph_summary") if isinstance(data, dict) else None,
            }
        ]
    else:
        index = FoundryIndex()
        candidates = index.get_render_candidates(limit=limit, kinds=kinds)

    # Build jobs.
    jobs: list[RenderJob] = []
    for cand in candidates[:limit]:
        cp = Path(cand["clip"])
        if not cp.is_file():
            continue
        ch = cand.get("chapter") or {}
        situation = _situation_from_clip(cp, cp.parent) or {}
        if cand.get("graph_summary"):
            gs = cand["graph_summary"]
            if isinstance(gs, dict):
                situation["home_score"] = (gs.get("climax") or {}).get("home_score") or situation.get("home_score", 0)
                situation["away_score"] = (gs.get("climax") or {}).get("away_score") or situation.get("away_score", 0)

        game_profile = config.outcome.game_profile.value
        try:
            get_game_profile(game_profile)
        except Exception:
            game_profile = "ncaa_football_27"

        job = RenderJob(
            source_clip=str(cp.resolve()),
            chapter=ch,
            situation=situation,
            buttons_summary=cand.get("buttons_summary") or {},
            game_profile=game_profile,
            session_id=config.session_id,
            style=style or studio.prompt_style,
            model=studio.model,
            duration=render_duration,
            resolution=studio.resolution,
            generate_audio=studio.generate_audio,
            output_dir=str(output_dir) if output_dir else None,
            created_ns=now_ns(),
        )
        jobs.append(job)

    if not jobs:
        return []

    queue.submit(jobs)
    log.info("Foundry Reels: queued %d render jobs", len(jobs))

    if wait:
        finished = queue.join(timeout=wait_timeout)
        if not finished:
            log.warning("Foundry Reels: timed out waiting for render jobs")
        return [queue.get_job(j.job_id) for j in jobs if j.job_id]

    return jobs
