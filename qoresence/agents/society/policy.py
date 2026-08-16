"""SocietyPolicy — digit strip, cooldown, hard denies."""

from __future__ import annotations

import re
import time
from typing import Any

from .types import KNOWN_ROLES, AgentPacket, AgentReceipt

SCORE_PAIR = re.compile(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b")
_TWITCH = re.compile(r"\b(twitch|irc|helix)\b", re.I)


class SocietyPolicy:
    def __init__(self, *, cooldown_s: float = 45.0, max_calls_per_hour: int = 30) -> None:
        self.cooldown_s = float(cooldown_s)
        self.max_calls_per_hour = int(max_calls_per_hour)
        self._last: dict[str, float] = {}
        self._hour: list[float] = []

    def allow_role(self, role: str, enabled: tuple[str, ...]) -> bool:
        return role in KNOWN_ROLES and role in enabled

    def cooldown_ok(self, role: str) -> bool:
        now = time.monotonic()
        last = self._last.get(role, 0.0)
        return (now - last) >= self.cooldown_s

    def mark(self, role: str) -> None:
        now = time.monotonic()
        self._last[role] = now
        self._hour = [t for t in self._hour if now - t < 3600.0]
        self._hour.append(now)

    def budget_ok(self) -> bool:
        now = time.monotonic()
        self._hour = [t for t in self._hour if now - t < 3600.0]
        return len(self._hour) < self.max_calls_per_hour

    def strip_digits(self, text: str, packet: AgentPacket) -> str:
        """Remove score pairs unless locked and matching situation."""
        if not text:
            return text
        sit = packet.situation or {}
        home = sit.get("home_score")
        away = sit.get("away_score")

        def _keep(m: re.Match[str]) -> str:
            ticket_id = packet.confirm_ticket_id or (sit.get("confirm_ticket_id") or "")
            if not packet.score_vlm_locked or not ticket_id:
                return "board"
            try:
                a, b = int(m.group(1)), int(m.group(2))
            except (TypeError, ValueError):
                return "board"
            if home is not None and away is not None and {a, b} == {int(home), int(away)}:
                return m.group(0)
            return "board"

        return SCORE_PAIR.sub(_keep, text)

    def deny_side_effects(self, text: str) -> str | None:
        if _TWITCH.search(text or ""):
            return "hard deny: no Twitch/IRC/Helix from society"
        return None

    def finalize(self, receipt: AgentReceipt, packet: AgentPacket) -> AgentReceipt:
        deny = self.deny_side_effects(receipt.text)
        text = self.strip_digits(receipt.text, packet)
        ok = deny is None
        if deny:
            text = deny
        receipt.text = text
        receipt.policy_ok = ok
        ticket_id = packet.confirm_ticket_id or (packet.situation or {}).get("confirm_ticket_id")
        if ticket_id and SCORE_PAIR.search(text or ""):
            receipt.refs = dict(receipt.refs or {})
            receipt.refs.setdefault("ticket_id", str(ticket_id))
        return receipt


def situation_scores(sit: dict[str, Any]) -> tuple[int | None, int | None]:
    h, a = sit.get("home_score"), sit.get("away_score")
    try:
        return (int(h) if h is not None else None, int(a) if a is not None else None)
    except (TypeError, ValueError):
        return None, None
