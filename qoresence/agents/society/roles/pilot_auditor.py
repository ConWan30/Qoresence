"""Session closeout metrics — local counts, optional Quicksilver summary."""

from __future__ import annotations

import json
from typing import Any

from qoresence.agents.society.types import AgentPacket, AgentReceipt


def _metrics(packet: AgentPacket) -> dict[str, Any]:
    health = packet.health or {}
    video = (health.get("state") or {}).get("video") or health.get("video") or {}
    coup = health.get("coupling") or (health.get("state") or {}).get("controller") or {}
    commits = packet.last_commits or []
    chats = [c for c in commits if "chat" in str(c.get("kind") or c.get("action") or "")]
    confirms = [c for c in commits if str(c.get("path") or "") == "confirm"]
    return {
        "capture_stable": bool(video.get("has_frame")) and float(video.get("age_s") or 99) < 1.0,
        "video_age_s": video.get("age_s"),
        "pushes": video.get("pushes") or video.get("frames"),
        "imu_bodied": bool(coup.get("imu_bodied")),
        "coupling": coup.get("coupling"),
        "commits": len(commits),
        "chat_lines": len(chats),
        "confirm_lines": len(confirms),
        "clip_hits": len(packet.clip_hits or []),
        "score_locked": packet.score_vlm_locked,
        "drive_id": (packet.drive_graph or {}).get("drive_id"),
    }


def run(packet: AgentPacket, *, complete=None) -> AgentReceipt | None:
    m = _metrics(packet)
    issues: list[str] = []
    if not m["capture_stable"]:
        issues.append("capture age high or no frame")
    if m["chat_lines"] > 12:
        issues.append("chat volume high")
    if not m["score_locked"] and m["confirm_lines"] == 0:
        issues.append("no confirm score lock this window")
    bullets = [
        f"capture_stable={m['capture_stable']} age={m['video_age_s']}",
        f"commits={m['commits']} confirm={m['confirm_lines']} clips={m['clip_hits']}",
        f"issues={issues or ['none']}",
    ]
    text = "\n".join(bullets)
    model = "rules"
    if complete and packet.score_vlm_locked is not None:
        extra = complete(
            "You summarize local session metrics. Observation plane only. "
            "Do not invent scores. Three short bullets max.",
            json.dumps(m, default=str)[:1200],
        )
        extra = (extra or "").strip()
        if extra:
            text = extra
            model = "reason"
    return AgentReceipt(
        role="pilot_auditor",
        action="audit",
        text=text,
        refs={"metrics": m, "issues": issues},
        model=model,
    )
