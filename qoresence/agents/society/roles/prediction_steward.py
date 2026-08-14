"""Draft prediction text when armed. Resolve stays confirm path."""

from __future__ import annotations

from qoresence.agents.society.types import AgentPacket, AgentReceipt


def run(packet: AgentPacket, *, complete=None) -> AgentReceipt | None:
    commits = packet.last_commits or []
    armed = any(
        str(c.get("kind") or "") in {"arm", "prediction_open"}
        or str(c.get("action") or "") in {"arm_prediction", "start_prediction"}
        for c in commits[-8:]
    )
    if not armed:
        return None
    sit = packet.situation or {}
    q = sit.get("quarter")
    down = sit.get("down")
    draft = "Will they convert this snap?"
    if down == 4:
        draft = "Will they convert 4th down?"
    elif sit.get("red_zone") or str(sit.get("field_position") or "").lower().startswith("opp"):
        draft = "Will they score on this red-zone trip?"
    if q:
        draft = draft.rstrip("?") + f" (Q{q})?"
    if complete:
        extra = complete(
            "Draft one short yes/no prediction question. No invented scores. No Twitch.",
            f"down={down} quarter={q} locked={packet.score_vlm_locked}",
        )
        extra = (extra or "").strip().split("?")[0]
        if extra:
            draft = extra[:90] + ("?" if "?" not in extra else "")
    return AgentReceipt(
        role="prediction_steward",
        action="advise",
        text=draft,
        refs={"kind": "prediction_draft"},
        model="rules",
    )
