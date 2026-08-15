"""Agent Society runtime — background ticks only. Never capture."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .bus import SocietyBus
from .config import AgentSocietyConfig
from .policy import SocietyPolicy
from .quicksilver import SocietyQuicksilver
from .roles import drive_coach, ghost_editor, pilot_auditor, prediction_steward, spam_warden
from .types import AgentPacket, AgentReceipt

log = logging.getLogger(__name__)

_ROLE_RUN = {
    "spam_warden": spam_warden.run,
    "pilot_auditor": pilot_auditor.run,
    "drive_coach": drive_coach.run,
    "ghost_editor": ghost_editor.run,
    "prediction_steward": prediction_steward.run,
}

_runtime: SocietyRuntime | None = None


def _locked(sit: dict[str, Any]) -> bool:
    if sit.get("score_vlm_locked") or sit.get("scoreboard_locked"):
        return True
    src = str(sit.get("score_source") or sit.get("scoreboard_source") or "")
    return src in {"vlm", "ocr", "scoreboard"}


def build_packet() -> AgentPacket:
    """In-process packet. No DShow. Foundry + timeline only."""
    sit: dict[str, Any] = {}
    graph: dict[str, Any] = {}
    commits: list[dict[str, Any]] = []
    hits: list[dict[str, Any]] = []
    health: dict[str, Any] = {}
    session_id = ""
    try:
        from qoresence.agents.session_timeline import get_session_timeline

        tl = get_session_timeline()
        snap = tl.snapshot(recent_n=16) if hasattr(tl, "snapshot") else {}
        commits = list(snap.get("recent") or [])[-12:]
        graph = snap.get("drive_graph") or {}
        session_id = str(snap.get("session_id") or "")
    except Exception:
        pass
    try:
        from qoresence.foundry.index import get_drive_graph, get_render_candidates

        hits = get_render_candidates(limit=4) or []
        if not graph:
            g = get_drive_graph()
            if isinstance(g, dict) and g.get("ok"):
                graph = g
    except Exception:
        pass
    try:
        from qoresence.agents.agent_glass import get_agent_glass

        g = get_agent_glass()
        if g is not None:
            gs = g.snapshot()
            sit = gs.get("situation") or sit
            health = {"video": gs.get("video"), "coupling": gs.get("coupling")}
            session_id = session_id or str((gs.get("session") or {}).get("session_id") or "")
    except Exception:
        pass
    return AgentPacket(
        session_id=session_id,
        clock_ns=time.monotonic_ns(),
        situation=sit if isinstance(sit, dict) else {},
        score_vlm_locked=_locked(sit if isinstance(sit, dict) else {}),
        drive_graph=graph if isinstance(graph, dict) else {},
        last_commits=commits,
        health=health,
        clip_hits=hits,
    )


class SocietyRuntime:
    def __init__(self, config: AgentSocietyConfig | None = None) -> None:
        self.config = config or AgentSocietyConfig.from_env()
        self.policy = SocietyPolicy(
            cooldown_s=self.config.cooldown_s,
            max_calls_per_hour=self.config.max_calls_per_hour,
        )
        self.qs = SocietyQuicksilver(self.config)
        self.bus = SocietyBus(mirror_timeline=self.config.mirror_timeline)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ticks = 0
        self._receipts = 0
        self._last: list[dict[str, Any]] = []

    def start(self) -> bool:
        if not self.config.enabled:
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="agent-society", daemon=True)
        self._thread.start()
        log.info(
            "Agent Society started roles=%s quicksilver=%s",
            ",".join(self.config.roles),
            self.qs.available(),
        )
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        log.info("Agent Society stopped")

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.config.enabled),
            "alive": bool(self._thread and self._thread.is_alive()),
            "roles": list(self.config.roles),
            "quicksilver": self.qs.available(),
            "key_file": self.config.api_key_file,
            "ticks": self._ticks,
            "receipts": self._receipts,
            "last": list(self._last[-5:]),
        }

    def _complete(self, system: str, user: str) -> str:
        if not self.qs.available() or not self.policy.budget_ok():
            return ""
        return self.qs.complete(system, user, model=self.config.model_reason)

    def tick(self, packet: AgentPacket | None = None, *, roles: tuple[str, ...] | None = None) -> list[AgentReceipt]:
        """One pass. Safe without start(). Rules-only if no key."""
        packet = packet or build_packet()
        want = roles or self.config.roles
        out: list[AgentReceipt] = []
        self._ticks += 1
        for role in want:
            if not self.policy.allow_role(role, self.config.roles if roles is None else want):
                continue
            if not self.policy.cooldown_ok(role):
                continue
            fn = _ROLE_RUN.get(role)
            if fn is None:
                continue
            try:
                rec = fn(packet, complete=self._complete)
            except Exception as e:
                log.debug("society role %s failed: %s", role, e)
                continue
            if rec is None:
                continue
            rec = self.policy.finalize(rec, packet)
            self.policy.mark(role)
            self.bus.publish(rec)
            out.append(rec)
        if out:
            self._receipts += len(out)
            self._last = (self._last + [r.to_dict() for r in out])[-12:]
        return out

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:
                log.debug("society tick: %s", e)
            self._stop.wait(timeout=max(15.0, self.config.cooldown_s))


def start_society(config: AgentSocietyConfig | None = None) -> SocietyRuntime | None:
    global _runtime
    cfg = config or AgentSocietyConfig.from_env()
    if not cfg.enabled:
        return None
    rt = SocietyRuntime(cfg)
    rt.start()
    _runtime = rt
    return rt


def stop_society() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None


def get_society() -> SocietyRuntime | None:
    return _runtime


def run_audit_once() -> AgentReceipt | None:
    cfg = AgentSocietyConfig.from_env()
    rt = SocietyRuntime(
        AgentSocietyConfig(
            enabled=True,
            roles=("pilot_auditor",),
            quicksilver_base=cfg.quicksilver_base,
            api_key_file=cfg.api_key_file,
            model_reason=cfg.model_reason,
            model_scene=cfg.model_scene,
            cooldown_s=0.0,
        )
    )
    recs = rt.tick(roles=("pilot_auditor",))
    return recs[0] if recs else None


def run_propose_cuts_once() -> AgentReceipt | None:
    cfg = AgentSocietyConfig.from_env()
    rt = SocietyRuntime(
        AgentSocietyConfig(
            enabled=True,
            roles=("ghost_editor",),
            quicksilver_base=cfg.quicksilver_base,
            api_key_file=cfg.api_key_file,
            model_reason=cfg.model_reason,
            cooldown_s=0.0,
        )
    )
    recs = rt.tick(roles=("ghost_editor",))
    return recs[0] if recs else None
