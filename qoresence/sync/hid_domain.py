"""HID domain classification — observe vs play pad.

Operator law (ConWan30): laptop DualSense Edge USB is an observe HID. The PS5
DualSense (wireless or wired to PS5) is the play pad. Ghost, PLL lock,
coupling_ticket, controller_bodied must NEVER arm from observe HID.

Domain detection:
- USB DualSense Edge on laptop: OBSERVE (vid=054c pid=0df2 transport=usb)
- All other Sony controllers: PLAY (PS5 wireless, PS5 wired, etc.)

Note: imu_echo and hid_output=0 stay probe facts. Pulse ≠ event. Never invent
PS5 rumble from laptop USB.
"""

from __future__ import annotations

import enum
import logging
from typing import Any

log = logging.getLogger(__name__)

# Sony DualSense / DualSense Edge
DS_EDGE_VID = 0x054C  # Sony
DS_EDGE_PID = 0x0DF2  # DualSense Edge Wireless Controller


class HidDomain(enum.Enum):
    """HID domain for play-pad bind."""

    OBSERVE = "observe"  # laptop USB Edge — observation only, no bind
    PLAY = "play"  # PS5 DualSense — the play pad


def classify_hid_domain(
    *,
    vid: int | None = None,
    pid: int | None = None,
    transport: str | None = None,
    product: str | None = None,
    path: str | None = None,
) -> HidDomain:
    """Classify HID as OBSERVE (laptop USB Edge) or PLAY (everything else).

    Args:
        vid: Vendor ID (e.g. 0x054c for Sony)
        pid: Product ID (e.g. 0x0df2 for Edge)
        transport: "usb" or "bt" or "unknown"
        product: Product string from HID enumerate
        path: HID device path

    Returns:
        HidDomain.OBSERVE if laptop USB DualSense Edge, else HidDomain.PLAY
    """
    # Default to PLAY unless we positively identify laptop USB Edge
    if vid is None or pid is None:
        return HidDomain.PLAY

    # Laptop USB DualSense Edge = observe
    if int(vid) == DS_EDGE_VID and int(pid) == DS_EDGE_PID:
        trans = str(transport or "").lower()
        if trans == "usb":
            log.info(
                "HID domain: OBSERVE (laptop USB DualSense Edge vid=%04x pid=%04x transport=%s)",
                vid,
                pid,
                transport,
            )
            return HidDomain.OBSERVE

    # Everything else = play pad
    return HidDomain.PLAY


def allow_bind(domain: HidDomain | str | None) -> bool:
    """Ghost, PLL, coupling_ticket, controller_bodied can only arm from PLAY."""
    if domain is None:
        return True  # legacy: no domain field → allow (fail-open until rollout)
    if isinstance(domain, HidDomain):
        return domain == HidDomain.PLAY
    return str(domain).lower() == HidDomain.PLAY.value


def allow_imu_bodied(domain: HidDomain | str | None) -> bool:
    """imu_bodied / imu_precursor can only be set from PLAY pad."""
    return allow_bind(domain)


def allow_coupling_ticket(domain: HidDomain | str | None) -> bool:
    """Coupling tickets can only be minted from PLAY pad HID."""
    return allow_bind(domain)


def allow_pll_observe_phase(domain: HidDomain | str | None) -> bool:
    """PLL phase observations can only come from PLAY pad."""
    return allow_bind(domain)


def domain_reason(domain: HidDomain | str | None) -> str:
    """Human-readable reason for domain veto."""
    if domain is None:
        return "no_domain"
    if isinstance(domain, HidDomain):
        return domain.value
    d = str(domain).lower()
    if d == HidDomain.OBSERVE.value:
        return "hid_observe"
    return d
