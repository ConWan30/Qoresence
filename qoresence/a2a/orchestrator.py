"""A2A orchestrator: scene → chat → policy → commit (background-safe)."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from typing import Any

from qoresence.a2a.bus import A2ABus
from qoresence.a2a.deepseek_agent import DeepSeekChatAgent
from qoresence.a2a.gemini_agent import GeminiSceneAgent
from qoresence.a2a.policy import A2APolicy
from qoresence.a2a.types import A2AMessage, ChatProposal, CommitAct, SceneProposal, Veto

log = logging.getLogger(__name__)


class A2AOrchestrator:
    """Sparse A2A cycle — never call from streamer grab thread synchronously."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        coupling_threshold: float = 0.45,
        min_interval_s: float = 20.0,
        on_commit: Callable[[CommitAct], None] | None = None,
        persona: str = "neutral",
    ) -> None:
        env_on = os.environ.get("QORESENCE_A2A", "0").strip() in {"1", "true", "yes"}
        self.enabled = env_on if enabled is None else bool(enabled)
        self.coupling_threshold = coupling_threshold
        self.min_interval_s = min_interval_s
        self.on_commit = on_commit
        self.bus = A2ABus()
        self.policy = A2APolicy()
        self.gemini = GeminiSceneAgent()
        self.deepseek = DeepSeekChatAgent(persona=persona)
        self._lock = threading.Lock()
        self._last_trigger = 0.0
        self._recent_commits: list[dict[str, Any]] = []
        self._inflight = False

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "gemini_live": self.gemini.live,
            "deepseek_live": self.deepseek.live,
            "bus": self.bus.stats(),
            "recent_commits": list(self._recent_commits[-8:]),
            "recent_vetos": list(self.policy.recent_vetos[-8:]),
        }

    def maybe_trigger_from_drive(
        self,
        *,
        situation: dict[str, Any] | None = None,
        coupling: float | None = None,
        drive_phase: str | None = None,
        frame_seq: int | None = None,
        jpeg_bytes: bytes | None = None,
        path: str = "fast",
        force: bool = False,
    ) -> None:
        """Schedule a sparse A2A cycle on a background thread if pressure is high."""
        if not self.enabled and not force:
            return
        phase_ok = drive_phase in {"pressure", "armed", "open", "active"}
        coup_ok = (coupling or 0) >= self.coupling_threshold
        if not force and not phase_ok and not coup_ok:
            return
        now = time.time()
        with self._lock:
            if self._inflight:
                return
            if not force and (now - self._last_trigger) < self.min_interval_s:
                return
            self._inflight = True
            self._last_trigger = now

        def _run() -> None:
            try:
                self.run_cycle(
                    situation=situation,
                    coupling=coupling,
                    drive_phase=drive_phase,
                    frame_seq=frame_seq,
                    jpeg_bytes=jpeg_bytes,
                    path=path,
                )
            finally:
                with self._lock:
                    self._inflight = False

        threading.Thread(target=_run, name="a2a-cycle", daemon=True).start()

    def run_cycle(
        self,
        *,
        situation: dict[str, Any] | None = None,
        coupling: float | None = None,
        drive_phase: str | None = None,
        frame_seq: int | None = None,
        jpeg_bytes: bytes | None = None,
        path: str = "fast",
    ) -> CommitAct | Veto | None:
        """Synchronous cycle (tests / forced). Prefer maybe_trigger_from_drive live."""
        sit = situation or {}
        scene = self.gemini.propose_scene(
            situation=sit,
            coupling=coupling,
            drive_phase=drive_phase,
            frame_seq=frame_seq,
            jpeg_bytes=jpeg_bytes,
        )
        self.bus.publish(
            A2AMessage(
                kind="scene_proposal",
                body=scene.to_dict(),
                from_agent="gemini",
                to_agent="deepseek",
            )
        )
        self._timeline("a2a_scene", scene.summary, path="fast", payload=scene.to_dict())

        chat = self.deepseek.propose_chat(scene, situation=sit, path=path)
        self.bus.publish(
            A2AMessage(
                kind="chat_proposal",
                body=chat.to_dict(),
                from_agent="deepseek",
                to_agent="policy",
            )
        )

        result = self.policy.evaluate(chat, sit)
        if isinstance(result, Veto):
            self.bus.publish(
                A2AMessage(
                    kind="veto",
                    body=result.to_dict(),
                    from_agent="policy",
                    to_agent="*",
                )
            )
            self._timeline("a2a_veto", result.reason, path="system", payload=result.to_dict())
            log.info("A2A veto: %s (%s)", result.reason, (result.rejected_text or "")[:60])
            return result

        self.bus.publish(
            A2AMessage(
                kind="commit_act",
                body=result.to_dict(),
                from_agent="policy",
                to_agent="clutchbot",
            )
        )
        self._timeline("a2a_commit", result.text, path=result.path, payload=result.to_dict())
        self._recent_commits.append(result.to_dict())
        if len(self._recent_commits) > 30:
            self._recent_commits = self._recent_commits[-30:]
        log.info("A2A commit path=%s: %s", result.path, result.text[:80])
        if self.on_commit:
            try:
                self.on_commit(result)
            except Exception as e:
                log.warning("A2A on_commit failed: %s", e)
        return result

    @staticmethod
    def _timeline(kind: str, message: str, *, path: str, payload: dict[str, Any]) -> None:
        try:
            from qoresence.agents.session_timeline import get_session_timeline

            get_session_timeline().append(
                kind=kind,
                path=path,
                message=message[:200],
                reason="a2a",
                factual=path == "confirm",
                payload=payload,
            )
        except Exception:
            pass


_orch: A2AOrchestrator | None = None
_orch_lock = threading.Lock()


def get_a2a_orchestrator(**kwargs: Any) -> A2AOrchestrator:
    global _orch
    with _orch_lock:
        if _orch is None:
            _orch = A2AOrchestrator(**kwargs)
        return _orch


def reset_a2a_orchestrator() -> A2AOrchestrator:
    global _orch
    with _orch_lock:
        _orch = A2AOrchestrator()
        return _orch
