"""Propose a local Ghost Cut window. Never LTX. Proposal only."""

from __future__ import annotations

from qoresence.agents.society.types import AgentPacket, AgentReceipt


def run(packet: AgentPacket, *, complete=None) -> AgentReceipt | None:
    hits = packet.clip_hits or []
    if not hits:
        return AgentReceipt(
            role="ghost_editor",
            action="advise",
            text="no Foundry candidates",
            model="rules",
        )
    top = hits[0]
    ch = top.get("chapter") if isinstance(top.get("chapter"), dict) else {}
    try:
        t = float(ch.get("t_s") or top.get("t_s") or 0.0)
    except (TypeError, ValueError):
        t = 0.0
    lab = str(ch.get("label") or top.get("label") or "play")
    t_in = max(0.0, t - 6.0)
    t_out = t + 12.0
    stem = str(top.get("name") or top.get("stem") or top.get("clip") or "")
    title = lab[:80]
    if complete:
        extra = complete(
            "Propose a local highlight title only. No invented scores. One short title.",
            f"chapter={lab} t={t:.2f} stem={stem}",
        )
        extra = (extra or "").strip().splitlines()[0] if extra else ""
        if extra:
            title = extra[:80]
    text = f"propose_cut {stem} {t_in:.1f}-{t_out:.1f}s · {title}"
    return AgentReceipt(
        role="ghost_editor",
        action="propose_cut",
        text=text,
        refs={
            "clip": stem,
            "t_s_in": round(t_in, 3),
            "t_s_out": round(t_out, 3),
            "title": title,
            "ghost_buttons": bool(top.get("onset_count") or top.get("buttons_summary")),
        },
        model="rules",
    )
