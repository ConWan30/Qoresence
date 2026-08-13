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
from .ghost_cut import buttons_from_sidecar, cut_highlight
from .receipt import now_ns

log = logging.getLogger(__name__)


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
    output_dir: str | None = None
    status: str = "pending"
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
            "output_dir": self.output_dir,
            "status": self.status,
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
            output_dir=d.get("output_dir"),
            status=d.get("status", "pending"),
            output_path=d.get("output_path", ""),
            error=d.get("error", ""),
            created_ns=d.get("created_ns") or now_ns(),
            started_ns=d.get("started_ns", 0),
            completed_ns=d.get("completed_ns", 0),
            metadata=d.get("metadata") or {},
        )


class ReelQueue:
    """Thread-safe background queue for local Ghost Cuts."""

    def __init__(
        self,
        frame_selector: FrameSelector,
        output_dir: str | Path = "clips",
        *,
        jobs_file: str | Path | None = None,
    ):
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
                self._worker = threading.Thread(target=self._worker_loop, daemon=True)
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
        """Wait until queued jobs finish. Does not stop the worker."""
        import time

        if timeout is None:
            self._queue.join()
            return True
        deadline = time.time() + float(timeout)
        while time.time() < deadline:
            if self._queue.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return self._queue.unfinished_tasks == 0

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
            out_dir = clip_path.parent / (clip_path.stem + "_cut")
        out_dir.mkdir(parents=True, exist_ok=True)

        t_s = float(job.chapter.get("t_s") or 0.0)
        png_path = self.frame_selector.extract_png(clip_path, t_s, out_dir / f"frame_{t_s:.3f}.png")
        if png_path is None:
            raise RuntimeError(f"Failed to extract frame from {clip_path}")

        buttons = job.buttons_summary or buttons_from_sidecar(clip_path)
        job.output_path = str(out_dir / f"reel_{job.job_id}.mp4")
        result = cut_highlight(
            clip_path,
            job.chapter,
            situation=job.situation,
            buttons_summary=buttons,
            output_path=job.output_path,
            session_id=job.session_id,
            game_profile=str(job.game_profile),
        )
        job.completed_ns = now_ns()
        job.status = "completed"
        self._save_jobs()
        log.info(
            "ReelQueue: Ghost Cut %s -> %s (%d frames)",
            job.source_clip,
            result.output_path,
            result.frames,
        )


# Process-wide singleton
_reel_queue: ReelQueue | None = None
_reel_queue_lock = threading.Lock()


def get_reel_queue() -> ReelQueue | None:
    return _reel_queue


def init_reel_queue(**kw: Any) -> ReelQueue:
    global _reel_queue
    with _reel_queue_lock:
        if _reel_queue is None:
            _reel_queue = ReelQueue(**kw)
        return _reel_queue


def reset_reel_queue() -> None:
    """Drop the process singleton. Used by tests and process teardown."""
    global _reel_queue
    with _reel_queue_lock:
        if _reel_queue is not None:
            try:
                _reel_queue.stop(wait=True, timeout=2.0)
            except Exception:
                pass
            _reel_queue = None
