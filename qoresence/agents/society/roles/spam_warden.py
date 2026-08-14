"""De-dupe / digit soft-path veto — rules first."""

from __future__ import annotations

import re
import time

from qoresence.agents.society.policy import SCORE_PAIR
from qoresence.agents.society.types import AgentPacket, AgentReceipt

_NORM = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return _NORM.sub(" ", (s or "").lower()).strip()[:80]


def run(packet: AgentPacket, *, complete=None) -> AgentReceipt | None:
    commits = packet.last_commits or []
    if not commits:
        return AgentReceipt(role="spam_warden", action="allow", text="no commits", model="rules")
    last = commits[-1]
    title = str(last.get("message") or last.get("title") or last.get("label") or "")
    path = str(last.get("path") or packet.path or "")
    if path == "fast" and SCORE_PAIR.search(title):
        return AgentReceipt(
            role="spam_warden",
            action="veto",
            text="soft path must not carry score digits",
            refs={"path": path},
            model="rules",
        )
    now = packet.clock_ns or time.monotonic_ns()
    nt = _norm(title)
    if nt:
        for prev in commits[:-1][-8:]:
            if _norm(str(prev.get("message") or prev.get("title") or "")) != nt:
                continue
            try:
                dts = abs(int(prev.get("clock_ns") or 0) - int(now))
            except (TypeError, ValueError):
                dts = 0
            if dts == 0 or dts < 90_000_000_000:
                return AgentReceipt(
                    role="spam_warden",
                    action="veto",
                    text="near-duplicate title in window",
                    refs={"title": title[:80]},
                    model="rules",
                )
    return AgentReceipt(role="spam_warden", action="allow", text="ok", model="rules")
