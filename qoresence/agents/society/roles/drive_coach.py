"""Post-drive ≤3 bullets. No Twitch. Observation-plane coach."""

from __future__ import annotations

import json

from qoresence.agents.society.types import AgentPacket, AgentReceipt


def run(packet: AgentPacket, *, complete=None) -> AgentReceipt | None:
    g = packet.drive_graph or {}
    if not g and not packet.last_commits:
        return None
    phase = g.get("phase") or g.get("drive_phase") or "idle"
    climax = g.get("climax") if isinstance(g.get("climax"), dict) else {}
    label = climax.get("best_label") or ""
    hits = packet.clip_hits or []
    phrase = getattr(packet, "phrase", "") or "IDLE"
    bullets = [
        f"Drive phase {phase}.",
        f"Phrase {phrase}. Climax: {label or 'none'}."[:120],
        f"Foundry hits this drive: {len(hits)}.",
    ]
    text = " ".join(bullets)
    model = "rules"
    if complete:
        extra = complete(
            "You are a local observation-plane coach. At most 3 bullets. "
            "No invented scores. No anti-cheat language. No Twitch.",
            json.dumps({"phase": phase, "climax": climax, "clips": len(hits)}, default=str)[:800],
        )
        extra = (extra or "").strip()
        if extra:
            text = extra
            model = "reason"
    return AgentReceipt(
        role="drive_coach",
        action="note",
        text=text[:400],
        refs={"drive_id": g.get("drive_id"), "phase": phase},
        model=model,
    )
