"""Fail-closed MCP witness pack — what an agent is allowed to say.

Observation plane only. Silence is a feature. No invented scores or public URLs.
"""

from __future__ import annotations

from typing import Any

PLANE = "qoresence-observation"


def _num(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _hydrate_control(
    control: dict[str, Any] | None,
    situation: dict[str, Any],
    clock_ns: int | None,
    seq: int | None,
) -> dict[str, Any] | None:
    """Attach pad-label wire when the caller omitted control. Fail closed."""
    if isinstance(control, dict):
        return control
    try:
        from qoresence.deck.observation_wire import build_observation_wire

        wire_sit = dict(situation) if isinstance(situation, dict) else {}
        if seq is not None and wire_sit.get("frame_seq") is None:
            wire_sit["frame_seq"] = seq
        if clock_ns is not None and wire_sit.get("clock_ns") is None:
            wire_sit["clock_ns"] = clock_ns
        if wire_sit.get("frame_seq") is None:
            return None
        return build_observation_wire(wire_sit)
    except Exception:
        return None


def build_observation(
    *,
    situation: dict[str, Any] | None = None,
    video: dict[str, Any] | None = None,
    coupling: dict[str, Any] | None = None,
    glass_link: dict[str, Any] | None = None,
    clock_ns: int | None = None,
    seq: int | None = None,
    control: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sit = situation if isinstance(situation, dict) else {}
    vid = video if isinstance(video, dict) else {}
    coup = coupling if isinstance(coupling, dict) else {}
    glass = glass_link if isinstance(glass_link, dict) else {}
    silence: list[str] = []
    control = _hydrate_control(control, sit, clock_ns, seq)

    title_locked = (
        bool(sit.get("title_claim")) or str(sit.get("title_hysteresis") or "") == "locked"
    )
    profile = sit.get("game_profile") or sit.get("game_title")
    if title_locked and profile:
        title = {
            "claim": True,
            "profile": str(profile),
            "hysteresis": sit.get("title_hysteresis") or "locked",
        }
    else:
        title = {"claim": False, "profile": None, "hysteresis": sit.get("title_hysteresis") or None}
        if sit.get("title_hysteresis") == "overlay-rejected":
            silence.append("title_overlay_rejected")
        elif not title_locked:
            silence.append("title_not_locked")

    score_locked = bool(sit.get("score_vlm_locked") or sit.get("scoreboard_locked"))
    hs, aws = _num(sit.get("home_score")), _num(sit.get("away_score"))
    if score_locked and hs is not None and aws is not None:
        score = {"claim": True, "home": hs, "away": aws}
    else:
        score = {"claim": False, "home": None, "away": None}
        silence.append("score_not_locked")

    phrase = coup.get("phrase") or sit.get("phrase")
    coupling_v = coup.get("coupling")
    try:
        coupling_f = float(coupling_v) if coupling_v is not None else None
    except (TypeError, ValueError):
        coupling_f = None
    if phrase or (coupling_f is not None and coupling_f > 0):
        pad = {
            "phrase": str(phrase) if phrase else None,
            "coupling": coupling_f,
            "frame_seq": coup.get("frame_seq") or vid.get("seq"),
        }
    else:
        pad = {
            "phrase": None,
            "coupling": None,
            "frame_seq": coup.get("frame_seq") or vid.get("seq"),
        }
        silence.append("no_coupling")

    lan = bool(glass.get("lan"))
    url = glass.get("url")
    if url and not lan:
        glass_out = {
            "url": str(url),
            "lan": False,
            "say": "localhost only — do not tell the operator this opens on a phone",
        }
        silence.append("glass_localhost_only")
    elif url and lan:
        glass_out = {
            "url": str(url),
            "lan": True,
            "say": "same Wi-Fi only — not a public stream",
        }
    else:
        glass_out = {"url": None, "lan": False, "say": "glass link unknown"}
        silence.append("glass_unknown")

    has_frame = bool(vid.get("has_frame"))
    if not has_frame:
        silence.append("no_frame")

    allowed: list[str] = []
    if title["claim"] and title["profile"]:
        allowed.append(f"title is {title['profile']}")
    if score["claim"]:
        allowed.append(f"score {score['home']}-{score['away']}")
    if pad.get("phrase") and pad["phrase"] not in {None, "IDLE"}:
        allowed.append(f"phrase {pad['phrase']}")
    if has_frame:
        allowed.append("FrameHub has a frame")
    if glass_out.get("lan") and glass_out.get("url"):
        allowed.append(f"phone glass at {glass_out['url']} (LAN opt-in)")

    ctrl_in = control if isinstance(control, dict) else {}
    hid_button = ctrl_in.get("hid_button")
    verb = ctrl_in.get("verb")
    mode = ctrl_in.get("mode")
    if hid_button:
        control_out: dict[str, Any] = {
            "plane": PLANE,
            "hid_button": str(hid_button),
            "verb": str(verb) if verb else None,
            "mode": str(mode) if mode else None,
            "visual_phase": ctrl_in.get("visual_phase"),
            "conflict": ctrl_in.get("conflict"),
            "frame_seq": ctrl_in.get("frame_seq") or pad.get("frame_seq"),
            "labeled": bool(verb),
        }
        if verb and mode:
            allowed.append(
                f"pad label {hid_button} = {verb} (sheet {mode})"
            )
        else:
            silence.append("control_unlabeled")
    else:
        control_out = {
            "plane": PLANE,
            "hid_button": None,
            "verb": None,
            "mode": None,
            "visual_phase": ctrl_in.get("visual_phase"),
            "conflict": None,
            "frame_seq": ctrl_in.get("frame_seq") or pad.get("frame_seq"),
            "labeled": False,
        }
        silence.append("no_control_edge")

    return {
        "ok": True,
        "plane": PLANE,
        "claim_ceiling": "observation_only",
        "title": title,
        "score": score,
        "pad": pad,
        "control": control_out,
        "video": {
            "has_frame": has_frame,
            "age_s": vid.get("age_s"),
            "frame_seq": pad.get("frame_seq"),
        },
        "glass": glass_out,
        "clock_ns": clock_ns,
        "seq": seq,
        "may_say": allowed,
        "must_not_invent": silence,
    }
