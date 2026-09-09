"""DeckLeaseLamp — observation-plane chrome. Subscribe-not-own.

Sight Glass / Retina Deck leases already-held FrameHub frames.
Default OFF. ``--play`` does not enable. No device open. No grab.
No last-good numbers. Dark when lease.ok is false or subscribe is missing.

Query-only: never emits bus events, never takes a lobe lock across fan-out.
"""

from __future__ import annotations

import os
from typing import Any

PLANE = "qoresence-observation"
ENV_NAME = "QORESENCE_DECK_LEASE_LAMP"
FLAG_NAME = "deck_lease_lamp"

_TRUE = frozenset({"1", "true", "yes", "on"})

_config_on = False


def set_config_enabled(value: bool) -> None:
    """CLI/config latch. Tests should prefer QORESENCE_DECK_LEASE_LAMP."""
    global _config_on
    _config_on = bool(value)


def enabled(config: Any | None = None) -> bool:
    env = os.environ.get(ENV_NAME, "").strip().lower()
    env_on = env in _TRUE
    cfg = bool(getattr(config, FLAG_NAME, False)) if config is not None else _config_on
    return bool(env_on or cfg)


def reset() -> None:
    global _config_on
    _config_on = False


def snapshot(
    *,
    lease: dict[str, Any] | None = None,
    hub: dict[str, Any] | None = None,
    webrtc: dict[str, Any] | None = None,
    lock_dir: Any | None = None,
    device: str = "USB3.0 Video",
) -> dict[str, Any] | None:
    """Operator glass payload. None when flag off. No bus emit. No digits."""
    if not enabled():
        return None
    lease_bag = _lease_bag(lease, lock_dir=lock_dir, device=device)
    hub_bag = _hub_bag(hub)
    rtc_bag = webrtc if isinstance(webrtc, dict) else _webrtc_bag()
    lease_ok = bool(lease_bag.get("ok"))
    subscribed = _subscribed(hub_bag, rtc_bag)
    lamp = "on" if lease_ok and subscribed else "dark"
    age = hub_bag.get("age_s")
    frames = int(hub_bag.get("publishes") or hub_bag.get("seq") or 0)
    return {
        "enabled": True,
        "plane": PLANE,
        "lamp": lamp,
        "ok": lamp == "on",
        "lease_ok": lease_ok,
        "owner": str(lease_bag.get("owner") or ""),
        "pid": int(lease_bag.get("pid") or 0),
        "device": str(lease_bag.get("device") or device),
        "subscribed": subscribed,
        "age_s": age,
        "frames": frames,
        "flag": FLAG_NAME,
    }


def attach_health(body: dict[str, Any]) -> dict[str, Any]:
    """Attach lamp to a /health body. Omits the field when flag off."""
    if not enabled():
        return body
    video: dict[str, Any] = {}
    state = body.get("state")
    if isinstance(state, dict) and isinstance(state.get("video"), dict):
        video = state["video"]
    hub = {
        "has_frame": bool(video.get("hub_has_frame")),
        "age_s": video.get("hub_age_s") if video.get("hub_age_s") is not None else video.get("age_s"),
        "publishes": int(video.get("frames") or video.get("hub_seq") or 0),
        "seq": int(video.get("hub_seq") or 0),
    }
    lease = body.get("lease") if isinstance(body.get("lease"), dict) else None
    webrtc = body.get("webrtc") if isinstance(body.get("webrtc"), dict) else None
    snap = snapshot(lease=lease, hub=hub, webrtc=webrtc)
    if snap is not None:
        body["deck_lease_lamp"] = snap
    return body


def _lease_bag(
    lease: dict[str, Any] | None,
    *,
    lock_dir: Any | None,
    device: str,
) -> dict[str, Any]:
    if isinstance(lease, dict):
        return lease
    try:
        from qoresence.capture.lease import lease_health

        return lease_health(lock_dir=lock_dir, device=device)
    except Exception:
        return {"ok": False, "owner": "", "device": device, "pid": 0}


def _hub_bag(hub: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(hub, dict):
        return hub
    try:
        from qoresence.monitor.frame_hub import get_frame_hub

        return get_frame_hub().stats()
    except Exception:
        return {"has_frame": False, "seq": 0, "publishes": 0, "age_s": None}


def _webrtc_bag() -> dict[str, Any]:
    try:
        from qoresence.deck.webrtc_hub import stats as webrtc_stats

        bag = webrtc_stats()
        return bag if isinstance(bag, dict) else {}
    except Exception:
        return {}


def _subscribed(hub: dict[str, Any], webrtc: dict[str, Any]) -> bool:
    if bool(hub.get("has_frame")):
        return True
    try:
        return int(webrtc.get("peers") or 0) > 0
    except (TypeError, ValueError):
        return False
