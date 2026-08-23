"""Retina Stem Conductor — situation-directed program, not OBS scenes.

Ports glass/src/lib/coupling/director.ts. Compute under lock; emit after release.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from qoresence.core.types import EventType, SourceLobe, clock_ns

log = logging.getLogger(__name__)

DirectorMode = Literal["watch", "prime", "armed", "hold", "encode"]
ClutchKind = Literal["quiet", "score_play", "climax", "window"]

CLIP_HOLD_MS = 60_000


@dataclass(frozen=True)
class DirectorInput:
    now: float
    hold_until: float
    clip_busy: bool
    companion_armed: bool
    red_zone: bool
    late: bool
    close: bool
    clutch_score: float
    clutch_kind: ClutchKind
    clutch_label: str
    clutch_why: str
    companion_why: str
    clip_worth: float


@dataclass(frozen=True)
class DirectorBrief:
    mode: DirectorMode
    why: str
    arm_hot: bool
    suggested: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "why": self.why,
            "arm_hot": self.arm_hot,
            "suggested": self.suggested,
        }


def should_clip(kind: str, clip_worth: float) -> bool:
    """Mirror glass clip.ts shouldClip."""
    if kind in ("score_play", "climax"):
        return True
    return float(clip_worth) >= 0.65


def auto_clip_allowed(hold_until: float, now: float) -> bool:
    return hold_until <= now


def _prime_why(ing: DirectorInput) -> str:
    bits: list[str] = []
    if ing.red_zone:
        bits.append("Red zone")
    if ing.late:
        bits.append("Late clock")
    if ing.close:
        bits.append("Close board")
    if ing.clutch_kind == "score_play":
        bits.append("Score play")
    elif ing.clutch_kind == "climax":
        bits.append("Climax")
    elif ing.clutch_kind == "window":
        bits.append("Clutch window")
    if bits:
        return " · ".join(bits)
    why = (ing.clutch_why or "").strip()
    if why and why != "no clutch pressure":
        return why
    return ing.clutch_label or "Take primed"


def director_brief(ing: DirectorInput) -> DirectorBrief:
    """Same priority as director.ts: encode > hold > armed > prime > watch."""
    if ing.clip_busy:
        return DirectorBrief(
            mode="encode", why="Encoding 30s from the HDMI ring", arm_hot=False
        )
    if ing.hold_until > ing.now:
        return DirectorBrief(mode="hold", why="HOLD — auto-clip silenced", arm_hot=False)
    if ing.companion_armed:
        extra = (ing.companion_why or "").strip()
        return DirectorBrief(
            mode="armed",
            why=f"CLIP ARMED — {extra}" if extra else "CLIP ARMED — clutch will cut this",
            arm_hot=True,
        )
    primed = (
        should_clip(ing.clutch_kind, ing.clip_worth)
        or ing.clutch_score >= 0.55
        or ing.red_zone
        or ing.late
    )
    if primed:
        return DirectorBrief(mode="prime", why=_prime_why(ing), arm_hot=True)
    return DirectorBrief(mode="watch", why="Watching — no take yet", arm_hot=False)


def director_reasons(moments: list[dict[str, Any]]) -> list[str]:
    rows: list[tuple[float, str]] = []
    for m in moments:
        title = str(m.get("title") or "")
        path = str(m.get("path") or "")
        icon = str(m.get("icon") or "")
        if icon == "🎬" or path in ("fast", "confirm") or "clip" in title.lower():
            rows.append((float(m.get("at") or 0), title))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [t for _at, t in rows[:3]]


class StemConductor:
    """Subscribe-only ingest; emit stem_program outside self._lock."""

    def __init__(
        self,
        bus: Any | None = None,
        *,
        situation_provider: Callable[[], dict[str, Any]] | None = None,
        session_head_ns: int | None = None,
    ) -> None:
        self.bus = bus
        self._situation_provider = situation_provider
        self._session_head_ns = session_head_ns
        self._lock = threading.Lock()
        self._hold_until = 0.0
        self._clip_busy = False
        self._companion_armed = False
        self._companion_why = ""
        self._red_zone = False
        self._late = False
        self._close = False
        self._clutch_score = 0.0
        self._clutch_kind: ClutchKind = "quiet"
        self._clutch_label = "watching"
        self._clutch_why = "no clutch pressure"
        self._clip_worth = 0.0
        self._last_brief: DirectorBrief | None = None
        self._unsub: Callable[[], None] | None = None

    def start(self) -> None:
        if self.bus is None:
            return
        self._unsub = self.bus.subscribe(self._on_event)
        self.maybe_emit()

    def stop(self) -> None:
        if self._unsub is not None:
            try:
                self._unsub()
            except Exception:
                pass
            self._unsub = None

    def note_clip_busy(self, busy: bool) -> None:
        with self._lock:
            self._clip_busy = bool(busy)
        self.maybe_emit()

    def note_hold_until(self, hold_until_ms: float) -> None:
        with self._lock:
            self._hold_until = float(hold_until_ms)
        self.maybe_emit()

    def note_kill(self) -> None:
        with self._lock:
            self._hold_until = 0.0
        self.maybe_emit()

    def _on_event(self, event: Any) -> None:
        """Ingest only. Never emit while holding the lock."""
        et = getattr(event, "type", None)
        et_val = getattr(et, "value", et)
        payload = getattr(event, "payload", None) or {}
        if not isinstance(payload, dict):
            payload = {}
        with self._lock:
            if et_val in ("coupling_score", "presence_report"):
                try:
                    self._clip_worth = float(
                        payload.get("coupling")
                        or payload.get("score")
                        or self._clip_worth
                    )
                except (TypeError, ValueError):
                    pass
            if et_val == "agent_action" and str(payload.get("action") or "") == "clip":
                self._clip_busy = True
            sit = None
            if self._situation_provider is not None:
                try:
                    sit = self._situation_provider()
                except Exception:
                    sit = None
            if isinstance(sit, dict):
                self._ingest_situation(sit)
            brief = self._brief_unlocked(now_ms=_now_ms())
            changed = self._last_brief is None or brief != self._last_brief
            if changed:
                self._last_brief = brief
                out = brief.to_payload()
            else:
                out = None
        if out is not None:
            self._emit(out)

    def _ingest_situation(self, sit: dict[str, Any]) -> None:
        rz = sit.get("red_zone")
        if rz is None:
            rz = sit.get("redzone")
        if rz is not None:
            self._red_zone = bool(rz)
        clk = sit.get("game_clock_s")
        if clk is None:
            clk = sit.get("clock_s")
        try:
            if clk is not None:
                self._late = float(clk) <= 120.0
        except (TypeError, ValueError):
            pass
        try:
            hs = sit.get("home_score")
            aws = sit.get("away_score")
            if hs is not None and aws is not None:
                self._close = abs(int(hs) - int(aws)) <= 8
        except (TypeError, ValueError):
            pass
        armed = sit.get("clip_armed")
        if armed is None:
            armed = (sit.get("companion") or {}).get("clip", {}).get("armed") if isinstance(sit.get("companion"), dict) else None
        if armed is not None:
            self._companion_armed = bool(armed)
        why = sit.get("companion_why") or sit.get("clutch_why")
        if why:
            self._companion_why = str(why)
        kind = str(sit.get("clutch_kind") or self._clutch_kind)
        if kind in ("quiet", "score_play", "climax", "window"):
            self._clutch_kind = kind  # type: ignore[assignment]
        try:
            if sit.get("clutch_score") is not None:
                self._clutch_score = float(sit["clutch_score"])
        except (TypeError, ValueError):
            pass

    def _brief_unlocked(self, now_ms: float) -> DirectorBrief:
        return director_brief(
            DirectorInput(
                now=now_ms,
                hold_until=self._hold_until,
                clip_busy=self._clip_busy,
                companion_armed=self._companion_armed,
                red_zone=self._red_zone,
                late=self._late,
                close=self._close,
                clutch_score=self._clutch_score,
                clutch_kind=self._clutch_kind,
                clutch_label=self._clutch_label,
                clutch_why=self._clutch_why,
                companion_why=self._companion_why,
                clip_worth=self._clip_worth,
            )
        )

    def maybe_emit(self) -> None:
        with self._lock:
            brief = self._brief_unlocked(now_ms=_now_ms())
            changed = self._last_brief is None or brief != self._last_brief
            if changed:
                self._last_brief = brief
                out = brief.to_payload()
            else:
                out = None
        if out is not None:
            self._emit(out)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            brief = self._last_brief or self._brief_unlocked(now_ms=_now_ms())
            return {
                "mode": brief.mode,
                "why": brief.why,
                "arm_hot": brief.arm_hot,
                "suggested": brief.suggested,
            }

    def _emit(self, payload: dict[str, Any]) -> None:
        if self.bus is None:
            return
        try:
            self.bus.emit_raw(
                source_lobe=SourceLobe.STEM,
                event_type=EventType.STEM_PROGRAM.value,
                payload=dict(payload),
                clock_ns_override=clock_ns(),
                session_head_ns=self._session_head_ns,
            )
        except Exception as e:
            log.debug("stem_program emit skipped: %s", e)
        try:
            from qoresence.deck.server import push_stem_program

            push_stem_program(payload)
        except Exception:
            pass


def _now_ms() -> float:
    import time

    return time.time() * 1000.0
