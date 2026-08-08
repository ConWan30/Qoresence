"""Local A2A policy — soft no digits; confirm digits must match OCR situation."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from qoresence.a2a.types import ChatProposal, CommitAct, Veto

# Score-like patterns: 31-38, 12–7, etc.
_SCORE_RE = re.compile(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b")
_DIGIT_RE = re.compile(r"\b\d{1,2}\b")


def _norm(text: str) -> str:
    t = (text or "").lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s\-']", "", t)
    return t[:100]


@dataclass
class A2APolicy:
    """Gate ChatProposal → CommitAct | Veto."""

    # Soft chat floor — stop feed spam
    chat_cooldown_s: float = 45.0
    duplicate_window_s: float = 180.0
    _last_commit_ts: float = 0.0
    _last_text: str = ""
    _recent_norms: list[tuple[float, str]] = field(default_factory=list)
    recent_vetos: list[str] = field(default_factory=list)

    def evaluate(
        self,
        proposal: ChatProposal,
        situation: dict[str, Any] | None = None,
    ) -> CommitAct | Veto:
        text = (proposal.text or "").strip()
        if not text or len(text) < 4:
            return self._veto("empty chat", text)

        now = time.time()
        if now - self._last_commit_ts < self.chat_cooldown_s:
            return self._veto("chat cooldown", text)

        n = _norm(text)
        if n and n == _norm(self._last_text):
            return self._veto("duplicate text", text)
        # Near-duplicate window
        self._recent_norms = [
            (t, s) for t, s in self._recent_norms if now - t < self.duplicate_window_s
        ]
        for t, prev in self._recent_norms:
            if n == prev or (len(n) >= 24 and n[:24] == prev[:24]):
                return self._veto("near-duplicate chat", text)

        soft = proposal.soft_only or proposal.path == "fast"
        if soft:
            if _SCORE_RE.search(text):
                return self._veto("soft path forbids score digits", text)
            if self._invents_score_digits(text, situation):
                return self._veto("soft path invents score digits", text)
            self._accept(now, text, n)
            return CommitAct(
                action="chat",
                text=text[:140],
                path="fast",
                factual=False,
                reason="a2a soft commit",
                payload={"model": proposal.model, "persona": proposal.persona},
            )

        # Confirm path: any score digits must match local situation
        if not self._digits_match_situation(text, situation or {}):
            return self._veto("confirm digits mismatch local OCR situation", text)

        self._accept(now, text, n)
        return CommitAct(
            action="chat",
            text=text[:140],
            path="confirm",
            factual=True,
            reason="a2a confirm commit",
            payload={"model": proposal.model, "persona": proposal.persona},
        )

    def _accept(self, now: float, text: str, norm: str) -> None:
        self._last_commit_ts = now
        self._last_text = text
        if norm:
            self._recent_norms.append((now, norm))
            self._recent_norms = self._recent_norms[-12:]

    def _veto(self, reason: str, text: str) -> Veto:
        self.recent_vetos.append(reason)
        if len(self.recent_vetos) > 40:
            self.recent_vetos = self.recent_vetos[-40:]
        return Veto(reason=reason, rejected_text=text[:120])

    @staticmethod
    def _invents_score_digits(text: str, situation: dict[str, Any] | None) -> bool:
        if _SCORE_RE.search(text):
            return True
        sit = situation or {}
        hs, aws = sit.get("home_score"), sit.get("away_score")
        found = [int(x) for x in _DIGIT_RE.findall(text) if 0 <= int(x) <= 99]
        if not found:
            return False
        multi = [n for n in found if n >= 10]
        if not multi:
            return False
        if hs is None and aws is None:
            return True  # soft path shouldn't invent board numbers
        allowed = {int(x) for x in (hs, aws) if x is not None}
        return any(n not in allowed for n in multi)

    @staticmethod
    def _digits_match_situation(text: str, situation: dict[str, Any]) -> bool:
        pair_matches = list(_SCORE_RE.finditer(text))
        hs = situation.get("home_score")
        aws = situation.get("away_score")
        if not pair_matches:
            return True
        if hs is None or aws is None:
            return False
        allowed = {(int(hs), int(aws)), (int(aws), int(hs))}
        for m in pair_matches:
            nums = re.findall(r"\d{1,2}", m.group(0))
            if len(nums) < 2:
                return False
            pair = (int(nums[0]), int(nums[1]))
            if pair not in allowed:
                return False
        return True
