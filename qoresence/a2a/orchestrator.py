"""A2A orchestrator: event-driven scene → chat → policy → commit.

Triggers are reason-coded (score change, menu exit, drive, coupling, ambient).
Never call from streamer grab thread synchronously.
"""

from __future__ import annotations

import logging
import os
import re
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

# Per-reason min intervals (seconds) — ambient is longest
_INTERVAL_BY_REASON: dict[str, float] = {
    "score_changed": 8.0,
    "menu_exit": 12.0,
    "drive_pressure": 20.0,
    "coupling": 25.0,
    "scene_tick": 45.0,  # ~1–2/min ambient scene with image
    "video_ambient": 90.0,  # rare video-only heartbeat
    "force": 0.0,
}


def _norm_chat(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-']", "", t)
    return t[:100]


class A2AOrchestrator:
    """Event-driven A2A cycle — sparse, de-duped, menu-aware."""

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
        self._last_reason: str | None = None
        self._recent_commits: list[dict[str, Any]] = []
        self._recent_norms: list[tuple[float, str]] = []  # (ts, norm_text)
        self._inflight = False
        self._last_sit_key: tuple[Any, ...] | None = None

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "gemini_live": self.gemini.live,
            "deepseek_live": self.deepseek.live,
            "last_reason": self._last_reason,
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
        reason: str | None = None,
    ) -> None:
        """Schedule a sparse A2A cycle if an allowed trigger fires.

        Preferred reasons: score_changed | menu_exit | drive_pressure | coupling | scene_tick
        Legacy: video_ambient (rare) when only football gameplay with no event.
        """
        if not self.enabled and not force:
            return
        sit = situation or {}
        cat = str(sit.get("game_category") or "").lower()
        gst = str(sit.get("game_state") or "").lower()
        is_football = cat in {"football", "ncaa_football", "ncaa"}
        is_gameplay = gst in {"gameplay", "playing", "in_game"}
        is_menu = gst in {"menu", "lobby", "hub", "paused"} or bool(sit.get("paused"))

        # Never hype on pure menu unless force
        if not force and is_menu and reason not in {"menu_exit", "force"}:
            return
        # Non-football silent unless force
        if not force and not is_football and reason not in {"force", "coupling"}:
            return

        phase_ok = drive_phase in {"pressure", "armed", "open", "active"}
        coup_ok = (coupling or 0) >= self.coupling_threshold

        # Infer reason if caller didn't set one
        if not reason:
            if force:
                reason = "force"
            elif phase_ok:
                reason = "drive_pressure"
            elif coup_ok:
                reason = "coupling"
            elif is_football and is_gameplay:
                reason = "video_ambient"
            else:
                return

        if not force:
            if reason == "video_ambient" and not (is_football and is_gameplay):
                return
            if reason == "drive_pressure" and not phase_ok:
                return
            if reason == "coupling" and not coup_ok:
                return
            if reason in {"score_changed", "menu_exit", "scene_tick"} and not is_football:
                return

        interval = _INTERVAL_BY_REASON.get(reason, self.min_interval_s)
        interval = max(interval, 0.0 if force else min(self.min_interval_s, interval))
        # Global floor unless force / score_changed
        if not force and reason not in {"score_changed", "menu_exit"}:
            interval = max(interval, float(self.min_interval_s) * 0.5)

        now = time.time()
        with self._lock:
            if self._inflight:
                return
            if not force and (now - self._last_trigger) < interval:
                return
            self._inflight = True
            self._last_trigger = now
            self._last_reason = reason

        log.info("A2A trigger reason=%s interval=%.0fs path=%s", reason, interval, path)

        def _run() -> None:
            try:
                self.run_cycle(
                    situation=situation,
                    coupling=coupling,
                    drive_phase=drive_phase,
                    frame_seq=frame_seq,
                    jpeg_bytes=jpeg_bytes,
                    path=path,
                    reason=reason or "unknown",
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
        reason: str = "unknown",
    ) -> CommitAct | Veto | None:
        """Synchronous cycle (tests / forced). Prefer maybe_trigger_from_drive live."""
        sit = situation or {}
        # Attach trigger reason into scene context for agents
        sit = {**sit, "_a2a_reason": reason}
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
        self._timeline("a2a_scene", scene.summary, path="fast", payload={**scene.to_dict(), "reason": reason})

        chat = self.deepseek.propose_chat(scene, situation=sit, path=path)
        self.bus.publish(
            A2AMessage(
                kind="chat_proposal",
                body=chat.to_dict(),
                from_agent="deepseek",
                to_agent="policy",
            )
        )

        # Near-duplicate vs recent commits (policy also de-dupes last text)
        if self._is_near_duplicate(chat.text):
            veto = Veto(reason="near-duplicate recent A2A chat", rejected_text=(chat.text or "")[:120])
            self.policy.recent_vetos.append(veto.reason)
            self.bus.publish(
                A2AMessage(kind="veto", body=veto.to_dict(), from_agent="policy", to_agent="*")
            )
            self._timeline("a2a_veto", veto.reason, path="system", payload=veto.to_dict())
            log.info("A2A veto: %s (%s)", veto.reason, (veto.rejected_text or "")[:60])
            return veto

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

        # Tag commit with reason
        try:
            result.payload = {**(result.payload or {}), "a2a_reason": reason}
        except Exception:
            pass

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
        self._remember_text(result.text)
        log.info("A2A commit path=%s reason=%s: %s", result.path, reason, result.text[:80])
        if self.on_commit:
            try:
                self.on_commit(result)
            except Exception as e:
                log.warning("A2A on_commit failed: %s", e)
        return result

    def _remember_text(self, text: str) -> None:
        n = _norm_chat(text)
        if not n:
            return
        now = time.time()
        self._recent_norms.append((now, n))
        self._recent_norms = [(t, s) for t, s in self._recent_norms if now - t < 300.0][-20:]

    def _is_near_duplicate(self, text: str) -> bool:
        n = _norm_chat(text)
        if not n:
            return True
        now = time.time()
        for t, prev in self._recent_norms:
            if now - t > 180.0:
                continue
            if n == prev:
                return True
            # shared prefix (same hype line variants)
            if len(n) >= 24 and len(prev) >= 24 and (n[:24] == prev[:24]):
                return True
        return False

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
