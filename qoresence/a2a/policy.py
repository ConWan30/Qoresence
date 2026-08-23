"""Local A2A policy — soft no digits; confirm digits must match OCR situation."""

from __future__ import annotations

import os
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

    # Soft chat floor — stop feed spam. Tunable via env.
    chat_cooldown_s: float = 25.0
    duplicate_window_s: float = 120.0
    _last_commit_ts: float = 0.0
    _last_text: str = ""
    _recent_norms: list[tuple[float, str]] = field(default_factory=list)
    recent_vetos: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        env_cd = os.environ.get("QORESENCE_A2A_CHAT_COOLDOWN_S", "").strip()
        if env_cd:
            try:
                self.chat_cooldown_s = float(env_cd)
            except ValueError:
                pass
        env_dw = os.environ.get("QORESENCE_A2A_DUPLICATE_WINDOW_S", "").strip()
        if env_dw:
            try:
                self.duplicate_window_s = float(env_dw)
            except ValueError:
                pass

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
        for _t, prev in self._recent_norms:
            if n == prev or (len(n) >= 40 and n[:40] == prev[:40]):
                return self._veto("near-duplicate chat", text)

        soft = proposal.soft_only or proposal.path == "fast"
        if soft:
            if not self._fast_licensed(situation):
                return self._veto("fast chat requires coupling ticket", text)
            if _SCORE_RE.search(text):
                return self._veto("soft path forbids score digits", text)
            if self._invents_score_digits(text, situation):
                return self._veto("soft path invents score digits", text)
            if self._heat_unlicensed(text, situation):
                return self._veto("heat speech requires coupling ticket", text)
            self._accept(now, text, n)
            return CommitAct(
                action="chat",
                text=text[:140],
                path="fast",
                factual=False,
                reason="a2a soft commit",
                payload={"model": proposal.model, "persona": proposal.persona},
            )

        # Confirm path: ticket or VLM lock, then digits must match the board
        if not self._confirm_licensed(situation):
            return self._veto("confirm chat requires ticket or score lock", text)
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
    def _fast_licensed(situation: dict[str, Any] | None) -> bool:
        try:
            from qoresence.sync.coupling_ticket import get_coupling_book
        except Exception:
            return False
        sit = situation or {}
        tid = str(sit.get("coupling_ticket_id") or "")
        book = get_coupling_book()
        if tid and book.get(tid) is not None:
            return True
        return book.latest_live() is not None

    @staticmethod
    def _confirm_licensed(situation: dict[str, Any] | None) -> bool:
        sit = situation or {}
        if sit.get("score_vlm_locked") or sit.get("scoreboard_locked"):
            return True
        tid = str(sit.get("confirm_ticket_id") or "")
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            book = get_ticket_book()
            if tid and book.get(tid) is not None:
                return True
            return book.latest() is not None
        except Exception:
            return False

    @staticmethod
    def _heat_unlicensed(text: str, situation: dict[str, Any] | None) -> bool:
        try:
            from qoresence.sync.coupling_ticket import get_coupling_book, heat_speech
        except Exception:
            return False
        if not heat_speech(text):
            return False
        sit = situation or {}
        tid = str(sit.get("coupling_ticket_id") or "")
        book = get_coupling_book()
        if tid and book.get(tid) is not None:
            return False
        return book.latest_live() is None

    @staticmethod
    def _invents_score_digits(text: str, situation: dict[str, Any] | None) -> bool:
        """Flag only explicit scoreline patterns (X-Y) in soft path.

        Bare multi-digit numbers (yardage, down, jersey numbers) are NOT
        treated as invented scores — that was too aggressive and vetoed
        natural football commentary like "gained 12 yards" or "3rd and 8".
        The _SCORE_RE check above already catches "31-38" style scorelines.
        """
        if _SCORE_RE.search(text):
            return True
        return False

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
