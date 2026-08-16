"""FastMomentEngine — realtime video+input path for two-speed ClutchBot.

``path=fast`` moments fire from last-known situation + IVC coupling **without**
waiting for a new OCR crop. Soft chat **never invents score digits**.

OCR / outcome scoring remains the factual referee (``path=confirm``).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .moment_scorer import ScoredMoment
from .situation_model import SituationState

log = logging.getLogger(__name__)

# Soft templates — no score digits, no fabricated numbers
_SOFT_CHAT = {
    "red_zone_heat": "Red-zone energy spike — something's cooking.",
    "close_late": "Late and tight — intensity is climbing.",
    "input_spike": "Controller heat on a live drive — eyes up.",
    "clutch_window": "Clutch window opening — pad and picture aligned.",
}

# Reject fabricated scores like 12-7, 21–14, etc. in soft messages
_SCORE_DIGIT_RE = re.compile(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b")


@dataclass
class FastMomentEngine:
    """Realtime scorer: situation context + coupling → soft actions."""

    # Coupling thresholds (observation co-occurrence only)
    chat_coupling: float = 0.40
    clip_coupling: float = 0.55
    arm_coupling: float = 0.50
    # Separate cooldowns from MomentScorer confirm path
    chat_cooldown_s: float = 45.0
    clip_cooldown_s: float = 75.0
    arm_cooldown_s: float = 90.0

    _last: dict[str, float] = field(default_factory=dict)
    _prediction_armed: bool = False
    _armed_at: float = 0.0

    def score_fast(
        self,
        situation: SituationState,
        coupling: dict[str, Any] | None = None,
        features: set[str] | None = None,
    ) -> list[ScoredMoment]:
        """Return fast-path moments. Empty when coupling quiet or no context."""
        t0 = time.perf_counter()
        try:
            features = features or {"chat", "clip"}
            coup = self._resolve_coupling(coupling)
            c = float(coup.get("coupling") or 0.0)
            energy = float(coup.get("input_energy") or 0.0)
            frame_seq = coup.get("frame_seq")
            buttons = list(coup.get("buttons") or [])

            # Graceful degrade: no controller / empty ring → stay quiet
            if c < self.chat_coupling and energy <= 0.0:
                return []

            if not self._has_live_context(situation):
                return []

            red = self._is_red_zone(situation)
            close = self._is_close(situation)
            late = self._is_late(situation)
            moments: list[ScoredMoment] = []

            # Soft chat — never include score digits. Heat lines need a coupling ticket.
            if "chat" in features and c >= self.chat_coupling:
                heat_ok = self._heat_ticket_ok(coup)
                key, msg = self._pick_soft_chat(red=red, close=close, late=late, heat_ok=heat_ok)
                if msg and self._cooldown_ok(f"fast_chat:{key}", self.chat_cooldown_s):
                    msg = self._sanitize_soft(msg)
                    moments.append(
                        ScoredMoment(
                            triggered=True,
                            weight=min(0.55 + 0.2 * c, 0.85),
                            action="chat",
                            message=msg,
                            reason=f"fast path soft chat ({key})",
                            cooldown_key=f"fast_{key}",
                            payload={
                                "path": "fast",
                                "factual": False,
                                "coupling": c,
                                "input_energy": energy,
                                "frame_seq": frame_seq,
                                "buttons": buttons[:8],
                            },
                        )
                    )

            # Clip intent — local Foundry; does not invent facts
            if "clip" in features and c >= self.clip_coupling and (red or (close and late)):
                if self._cooldown_ok("fast_clip", self.clip_cooldown_s):
                    moments.append(
                        ScoredMoment(
                            triggered=True,
                            weight=min(0.7 + 0.25 * c, 0.95),
                            action="clip",
                            message="",
                            reason="fast path clip intent (video+input co-occurrence)",
                            cooldown_key="fast_clip",
                            payload={
                                "path": "fast",
                                "factual": False,
                                "coupling": c,
                                "frame_seq": frame_seq,
                                "seconds": 8.0,
                            },
                        )
                    )

            # Arm prediction latch — confirm path may start/resolve later
            if "prediction" in features and c >= self.arm_coupling and red:
                if self._cooldown_ok("fast_arm", self.arm_cooldown_s):
                    self._prediction_armed = True
                    self._armed_at = time.time()
                    moments.append(
                        ScoredMoment(
                            triggered=True,
                            weight=0.5,
                            action="arm_prediction",
                            message="",
                            reason="fast path armed prediction (await OCR confirm)",
                            cooldown_key="fast_arm",
                            payload={
                                "path": "fast",
                                "factual": False,
                                "coupling": c,
                                "frame_seq": frame_seq,
                                "armed": True,
                            },
                        )
                    )

            return moments
        finally:
            try:
                from qoresence.observability import record_latency

                record_latency("fast_moment", (time.perf_counter() - t0) * 1000.0)
            except Exception:
                pass

    def on_confirm_score(self) -> None:
        """Clear prediction arm latch when confirm path sees score change."""
        self._prediction_armed = False
        self._armed_at = 0.0

    def prediction_armed(self) -> bool:
        # Expire arm after 3 minutes if confirm never lands
        if self._prediction_armed and (time.time() - self._armed_at) > 180.0:
            self._prediction_armed = False
        return self._prediction_armed

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_coupling(coupling: dict[str, Any] | None) -> dict[str, Any]:
        if coupling is not None:
            return coupling
        try:
            from qoresence.sync.ivc import get_last_coupling

            return get_last_coupling()
        except Exception:
            return {"coupling": 0.0, "input_energy": 0.0, "buttons": [], "path": "fast"}

    @staticmethod
    def _has_live_context(state: SituationState) -> bool:
        if state.game_state and state.game_state != "gameplay":
            # Allow if we still have football fields from prior OCR
            pass
        # Need some known situation — not cold start
        if state.game_category in ("football", "Football") or state.game_profile:
            return True
        if state.field_position or state.quarter is not None or state.down is not None:
            return True
        if state.home_score is not None or state.away_score is not None:
            return True
        # Shooter fallback: kills known
        if state.kills is not None:
            return True
        return False

    @staticmethod
    def _is_red_zone(state: SituationState) -> bool:
        pos = (state.field_position or "").lower()
        if "opp" in pos:
            m = re.search(r"opp(?:onent)?\s*(\d+)", pos)
            if m and int(m.group(1)) <= 20:
                return True
        if "red" in pos and "zone" in pos:
            return True
        return False

    @staticmethod
    def _is_close(state: SituationState) -> bool:
        try:
            if state.home_score is None or state.away_score is None:
                return False
            return abs(int(state.home_score) - int(state.away_score)) <= 8
        except Exception:
            return False

    @staticmethod
    def _is_late(state: SituationState) -> bool:
        q = state.quarter
        try:
            return q is not None and int(q) >= 4
        except Exception:
            return False

    @staticmethod
    def _heat_ticket_ok(coup: dict[str, Any]) -> bool:
        tid = str(coup.get("coupling_ticket_id") or "")
        try:
            from qoresence.sync.coupling_ticket import get_coupling_book

            live = get_coupling_book().latest_live()
            if live is None:
                return False
            if tid and live.ticket_id != tid:
                return bool(get_coupling_book().get(tid))
            return True
        except Exception:
            return False

    def _pick_soft_chat(
        self, *, red: bool, close: bool, late: bool, heat_ok: bool = False
    ) -> tuple[str, str]:
        if red and (close or late):
            if heat_ok:
                return "clutch_window", _SOFT_CHAT["clutch_window"]
            return "red_zone_heat", _SOFT_CHAT["red_zone_heat"]
        if red:
            return "red_zone_heat", _SOFT_CHAT["red_zone_heat"]
        if close and late:
            return "close_late", _SOFT_CHAT["close_late"]
        if heat_ok:
            return "input_spike", _SOFT_CHAT["input_spike"]
        return "", ""

    @staticmethod
    def _sanitize_soft(msg: str) -> str:
        """Strip any accidental score-like digit patterns from soft chat."""
        cleaned = _SCORE_DIGIT_RE.sub("the scoreboard", msg)
        # Also drop lone "score: 14" style
        cleaned = re.sub(r"\bscore\s*[:=]?\s*\d+\b", "the scoreboard", cleaned, flags=re.I)
        return cleaned

    def _cooldown_ok(self, key: str, seconds: float) -> bool:
        now = time.time()
        last = self._last.get(key, 0.0)
        if now - last < seconds:
            return False
        self._last[key] = now
        return True


def soft_chat_has_score_digits(message: str) -> bool:
    """Test helper: True if message looks like it invents a scoreline."""
    if not message:
        return False
    return bool(_SCORE_DIGIT_RE.search(message))
