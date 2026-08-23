"""Stem audio device resolve — capture-card audio pin only. Never a laptop mic."""

from __future__ import annotations

_CARD_AUDIO_HINTS = (
    "hdmi",
    "usb3.0",
    "usb 3.0",
    "elgato",
    "avermedia",
    "game capture",
    "live gamer",
    "capture card",
    "digital audio (hdmi)",
    "usb3.0 audio",
)

_DENY_HINTS = (
    "microphone",
    "headset",
    "webcam",
    "camera",
    "brio",
    "integrated",
    "realtek",
    "array",
    "laptop",
    "internal",
    "default",
)


def is_capture_card_audio(name: str | None) -> bool:
    """True only for named HDMI / capture-card audio — never a laptop mic."""
    if not name:
        return False
    n = name.lower()
    if any(h in n for h in _DENY_HINTS):
        # HDMI capture often includes "digital" — deny wins unless a card hint is stronger
        if not any(h in n for h in ("hdmi", "elgato", "avermedia", "usb3", "capture card", "live gamer")):
            return False
        if any(h in n for h in ("microphone", "headset", "webcam", "camera", "brio", "laptop")):
            return False
    return any(h in n for h in _CARD_AUDIO_HINTS)


def is_denied_audio(name: str | None) -> bool:
    if not name:
        return True
    n = name.lower()
    if is_capture_card_audio(name):
        return False
    return any(h in n for h in _DENY_HINTS) or n in {"default", "communications"}


def resolve_audio_device(
    devices: list[tuple[int, str]],
    *,
    prefer_name: str | None = None,
) -> tuple[int, str] | None:
    """Pick a capture-card audio device. None if only mics / unplugged."""
    allowed = [(int(i), n) for i, n in devices if is_capture_card_audio(n)]
    if prefer_name:
        pn = prefer_name.strip().lower()
        for idx, name in allowed:
            nl = name.lower()
            if nl == pn or pn in nl or nl in pn:
                return idx, name
    if not allowed:
        return None
    for idx, name in allowed:
        if "usb3" in name.lower() or "hdmi" in name.lower():
            return idx, name
    return allowed[0]


def list_audio_devices() -> list[tuple[int, str]]:
    """Enumerate host audio inputs. Empty if no backend. Never invent a default mic."""
    try:
        import sounddevice as sd  # type: ignore[import-untyped]

        out: list[tuple[int, str]] = []
        for i, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels") or 0) <= 0:
                continue
            out.append((i, str(info.get("name") or f"device-{i}")))
        return out
    except Exception:
        return []
