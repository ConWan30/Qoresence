"""Asynchronous render queue for Foundry Reels.

Runs on a background thread. Does NOT touch the event bus or hold lobe locks.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Queue
from typing import Any

from .frame_selector import FrameSelector
from .ltx_client import LtxClient
from .prompt_engine import PromptEngine
from .receipt import ReelReceipt, now_ns, write_receipt

log = logging.getLogger(__name__)


def _sha256_hash(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


@dataclass
class RenderJob:
    """One queued render."""

    job_id: str = ""
    source_clip: str = ""
    chapter: dict[str, Any] = field(default_factory=dict)
    situation: dict[str, Any] | None = None
    buttons_summary: dict[str, int] | None = None
    game_profile: str = ""
    session_id: str = ""
    style: str = "cinematic"
    output_dir: str | None = None
    status: str = "pending"
    ltx_job_id: str = ""
    output_path: str = ""
    error: str = ""
    created_ns: int = field(default_factory=now_ns)
    started_ns: int = 0
    completed_ns: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source_clip": self.source_clip,
            "chapter": self.chapter,
            "situation": self.situation,
            "buttons_summary": self.buttons_summary,
            "game_profile": self.game_profile,
            "session_id": self.session_id,
            "style": self.style,
            "output_dir": self.output_dir,
            "status": self.status,
            "ltx_job_id": self.ltx_job_id,
            "output_path": self.output_path,
            "error": self.error,
            "created_ns": self.created_ns,
            "started_ns": self.started_ns,
            "completed_ns": self.completed_ns,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RenderJob:
        return cls(
            job_id=d.get("job_id", ""),
            source_clip=d.get("source_clip", ""),
            chapter=d.get("chapter") or {},
            situation=d.get("situation"),
            buttons_summary=d.get("buttons_summary"),
            game_profile=d.get("game_profile", ""),
            session_id=d.get("session_id", ""),
            style=d.get("style", "cinematic"),
            output_dir=d.get("output_dir"),
            status=d.get("status", "pending"),
            ltx_job_id=d.get("ltx_job_id", ""),
            output_path=d.get("output_path", ""),
            error=d.get("error", ""),
            created_ns=d.get("created_ns") or now_ns(),
            started_ns=d.get("started_ns", 0),
            completed_ns=d.get("completed_ns", 0),
            metadata=d.get("metadata") or {},
        )


class ReelQueue:
    """Thread-safe background queue for LTX reels."""

    def __init__(
        self,
        client: LtxClient,
        prompt_engine: PromptEngine,
        frame_selector: FrameSelector,
        output_dir: str | Path = "clips",
        *,
        jobs_file: str | Path | None = None,
    ):
        self.client = client
        self.prompt_engine = prompt_engine
        self.frame_selector = frame_selector
        self.output_dir = Path(output_dir)
        self.jobs_file = Path(jobs_file) if jobs_file else self.output_dir / "reels" / "jobs.jsonl"
        self._queue: Queue[RenderJob | None] = Queue()
        self._lock = threading.Lock()
        self._jobs: dict[str, RenderJob] = {}
        self._worker: threading.Thread | None = None
        self._stopped = threading.Event()
        self._load_jobs()

    def _load_jobs(self) -> None:
        if not self.jobs_file.is_file():
            return
        try:
            for line in self.jobs_file.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                d = json.loads(line)
                job = RenderJob.from_dict(d)
                self._jobs[job.job_id] = job
        except Exception as e:
            log.debug("ReelQueue load jobs failed: %s", e)

    def _save_jobs(self) -> None:
        try:
            self.jobs_file.parent.mkdir(parents=True, exist_ok=True)
            with self.jobs_file.open("w", encoding="utf-8") as f:
                for job in self._jobs.values():
                    f.write(json.dumps(job.to_dict()) + "\n")
        except Exception as e:
            log.warning("ReelQueue save jobs failed: %s", e)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._stopped.clear()
                self._worker = threading.Thread(target=self._worker_loop, daemon=False)
                self._worker.start()

    def submit(self, jobs: list[RenderJob]) -> list[str]:
        """Queue one or more render jobs."""
        if not jobs:
            return []
        self._ensure_worker()
        ids: list[str] = []
        for job in jobs:
            if not job.job_id:
                job.job_id = uuid.uuid4().hex[:12]
            with self._lock:
                self._jobs[job.job_id] = job
            self._queue.put(job)
            ids.append(job.job_id)
        self._save_jobs()
        return ids

    def get_job(self, job_id: str) -> RenderJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> list[RenderJob]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.created_ns, reverse=True)
        return jobs[:limit]

    def stop(self, wait: bool = True, timeout: float | None = None) -> None:
        """Signal the worker to finish current jobs and stop."""
        self._queue.put(None)
        self._stopped.set()
        if wait and self._worker and self._worker.is_alive():
            self._worker.join(timeout=timeout)

    def join(self, timeout: float | None = None) -> bool:
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=timeout)
            return not self._worker.is_alive()
        return True

    def _worker_loop(self) -> None:
        while not self._stopped.is_set():
            job = self._queue.get()
            if job is None:
                break
            try:
                self._process_job(job)
            except Exception as e:
                log.exception("ReelQueue: job %s failed", job.job_id)
                with self._lock:
                    job.status = "failed"
                    job.error = str(e)
                self._save_jobs()
            self._queue.task_done()

    def _process_job(self, job: RenderJob) -> None:
        job.started_ns = now_ns()
        job.status = "processing"
        self._save_jobs()

        # 1. Determine output directory.
        clip_path = Path(job.source_clip)
        if job.output_dir:
            out_dir = Path(job.output_dir)
        else:
            out_dir = clip_path.parent / (clip_path.stem + "_ltx")
        out_dir.mkdir(parents=True, exist_ok=True)

        # 2. Extract frame.
        t_s = float(job.chapter.get("t_s") or 0.0)
        png_path = self.frame_selector.extract_png(clip_path, t_s, out_dir / f"frame_{t_s:.3f}.png")
        if png_path is None:
            raise RuntimeError(f"Failed to extract frame from {clip_path}")

        # 3. Build prompt.
        from qoresence.core.unified_config import get_game_profile

        try:
            profile = get_game_profile(job.game_profile)
        except Exception:
            profile = get_game_profile("ncaa_football_27")

        payload = self.prompt_engine.build_payload(
            profile,
            job.chapter,
            situation=job.situation,
            buttons_summary=job.buttons_summary,
            style=job.style,
        )

        # 4. Render.
        job.output_path = str(out_dir / f"reel_{job.job_id}.mp4")
        ltx_job = self.client.render(
            png_path,
            payload.prompt,
            job.output_path,
            model=payload.model,
            duration=payload.duration,
            resolution=payload.resolution,
            aspect_ratio=payload.aspect_ratio,
            fps=payload.fps,
            generate_audio=payload.generate_audio,
        )

        job.completed_ns = now_ns()
        job.ltx_job_id = ltx_job.job_id

        if ltx_job.status != "completed":
            job.status = ltx_job.status or "failed"
            job.error = ltx_job.error or "LTX render failed"
            self._save_jobs()
            return

        # 5. Write receipt.
        receipt = ReelReceipt(
            session_id=job.session_id,
            clock_ns=job.situation.get("clock_ns") if job.situation else 0,
            source_clip=str(job.source_clip),
            source_t_s=t_s,
            ltx_job_id=ltx_job.job_id,
            ltx_prompt=payload.prompt,
            ltx_payload_hash=_sha256_hash(payload.prompt + str(job.game_profile)),
            output_path=job.output_path,
            output_url=ltx_job.video_url or "",
            created_ns=job.created_ns,
            completed_ns=job.completed_ns,
            status="completed",
            game_profile=str(job.game_profile),
            chapter_kind=str(job.chapter.get("kind") or ""),
            chapter_label=str(job.chapter.get("label") or ""),
            metadata={"negative_prompt": payload.negative_prompt, "model": payload.model},
        )
        write_receipt(job.output_path, receipt)

        job.status = "completed"
        self._save_jobs()
        log.info(
            "ReelQueue: finished %s -> %s (LTX job %s)",
            job.source_clip,
            job.output_path,
            ltx_job.job_id,
        )


# Process-wide singleton
_reel_queue: ReelQueue | None = None
_reel_queue_lock = threading.Lock()


def get_reel_queue() -> ReelQueue | None:
    return _reel_queue


def init_reel_queue(client: LtxClient, prompt_engine: PromptEngine, **kw: Any) -> ReelQueue:
    global _reel_queue
    with _reel_queue_lock:
        if _reel_queue is None:
            _reel_queue = ReelQueue(client, prompt_engine, **kw)
        return _reel_queue
