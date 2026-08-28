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

log = logging.getLogger(__name__)

# Sony DualSense / DualSense Edge
DS_EDGE_VID = 0x054C  # Sony
DS_EDGE_PID = 0x0DF2  # DualSense Edge Wireless Controller


class HidDomain(enum.Enum):
    """HID domain for play-pad bind."""

    OBSERVE = "observe"  # laptop USB Edge — observation only, no bind
    PLAY = "play"  # PS5 DualSense — the play pad
    PICTURE = "picture"  # HDMI HUD control legend — observation only, no bind


def rank_hid_collection(*, usage_page: int | None = None, usage: int | None = None) -> int:
    """Lower is better. DualSense gamepad collection first; vendor/touchpad last."""
    page = int(usage_page or 0)
    use = int(usage or 0)
    if page == 0x01 and use in {0x04, 0x05}:  # Generic Desktop Joystick / Gamepad
        return 0
    if page == 0x01:
        return 1
    if page >= 0xFF00:
        return 8
    return 5


def infer_transport(
    *,
    transport: str | None = None,
    path: str | None = None,
    bus_type: int | None = None,
) -> str | None:
    """Infer usb vs bt from hidapi bus_type / path when transport is unset.

    Used so DualSense Edge USB is OBSERVE at open, before the first parsed report.
    """
    t = str(transport or "").strip().lower()
    if t in {"usb", "wired"}:
        return "usb"
    if t in {"bt", "bluetooth", "wireless"}:
        return "bt"

    if bus_type is not None:
        try:
            bt = int(bus_type)
        except (TypeError, ValueError):
            bt = None
        else:
            # hidapi: HID_API_BUS_USB=1, HID_API_BUS_BLUETOOTH=2
            if bt == 1:
                return "usb"
            if bt == 2:
                return "bt"

    p = str(path or "").lower()
    if not p:
        return None
    if "bthenum" in p or "bluetooth" in p or "&col01" in p and "bth" in p:
        return "bt"
    if "vid_" in p or "vid=" in p or "&mi_" in p or "usb" in p or "hid#" in p:
        if "bth" not in p and "bluetooth" not in p:
            return "usb"
    return None


def classify_hid_domain(
    *,
    vid: int | None = None,
    pid: int | None = None,
    transport: str | None = None,
    product: str | None = None,
    path: str | None = None,
    bus_type: int | None = None,
) -> HidDomain:
    """Classify HID as OBSERVE (laptop USB Edge) or PLAY (everything else).

    Args:
        vid: Vendor ID (e.g. 0x054c for Sony)
        pid: Product ID (e.g. 0x0df2 for Edge)
        transport: "usb" or "bt" or "unknown"
        product: Product string from HID enumerate
        path: HID device path
        bus_type: hidapi bus_type (1=usb, 2=bluetooth)

    Returns:
        HidDomain.OBSERVE if laptop USB DualSense Edge, else HidDomain.PLAY
    """
    # Default to PLAY unless we positively identify laptop USB Edge
    if vid is None or pid is None:
        return HidDomain.PLAY

    # Laptop USB DualSense Edge = observe
    if int(vid) == DS_EDGE_VID and int(pid) == DS_EDGE_PID:
        trans = infer_transport(transport=transport, path=path, bus_type=bus_type)
        if trans == "usb":
            log.info(
                "HID domain: OBSERVE (laptop USB DualSense Edge vid=%04x pid=%04x transport=%s)",
                vid,
                pid,
                trans,
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
    if d == HidDomain.PICTURE.value:
        return "hid_picture"
    return d
