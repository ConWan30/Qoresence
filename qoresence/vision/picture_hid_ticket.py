"""Picture HID ticket — HDMI HUD control legend licensed onto FrameHub seq.

Sibling of ConfirmTicket, not a ConfirmTicket and not a coupling ticket.
Mint only from seeing-path vision (gemini / quicksilver). Never write
picture presses into InputRing. hid_domain=picture never binds.

Fail-closed: unlabeled when the frame does not show a named DualSense
callout. Never infer R2/stick from locomotion or visual_phase.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from qoresence.sync.hid_domain import HidDomain
from qoresence.vision.confirm_ticket import is_seeing_source, normalize_source

DOMAIN = "QORESENCE-PICTURE-HID-TICKET-v0"

# Control glyphs are VLM/HUD, not EasyOCR scorebug.
PICTURE_HID_SOURCES = frozenset({"gemini", "quicksilver"})

BUTTON_ALLOWLIST = frozenset(
    {
        "Cross",
        "Circle",
        "Square",
        "Triangle",
        "L1",
        "R1",
        "L2",
        "R2",
        "CREATE",
        "OPTIONS",
        "L3",
        "R3",
    }
)

_GLYPH_TO_BUTTON = {
    "✕": "Cross",
    "✖": "Cross",
    "×": "Cross",
    "x": "Cross",
    "cross": "Cross",
    "○": "Circle",
    "o": "Circle",
    "circle": "Circle",
    "□": "Square",
    "■": "Square",
    "square": "Square",
    "△": "Triangle",
    "▲": "Triangle",
    "triangle": "Triangle",
    "l1": "L1",
    "r1": "R1",
    "l2": "L2",
    "r2": "R2",
    "create": "CREATE",
    "share": "CREATE",
    "options": "OPTIONS",
    "l3": "L3",
    "r3": "R3",
}

_CHORD_RE = re.compile(r"[+,]|left stick|right stick|stick", re.IGNORECASE)


class PictureHidTicketSourceError(ValueError):
    """Raised when mint is attempted from a non-seeing-path source."""


class PictureHidTicketError(ValueError):
    """Raised when mint is refused (unknown button, analog, not gameplay)."""


def is_picture_hid_source(source: str | None) -> bool:
    """True when source may license a PictureHidTicket (gemini / quicksilver)."""
    if not source:
        return False
    s = normalize_source(source)
    if s not in PICTURE_HID_SOURCES:
        return False
    return is_seeing_source(s)


def normalize_hid_button(raw: str | None, *, glyph: str | None = None) -> str | None:
    """Map VLM button / glyph to DualSense allowlist name, or None."""
    for candidate in (raw, glyph):
        if candidate is None:
            continue
        s = str(candidate).strip()
        if not s or s.lower() in {"null", "none"}:
            continue
        if _CHORD_RE.search(s):
            return None
        if s in BUTTON_ALLOWLIST:
            return s
        mapped = _GLYPH_TO_BUTTON.get(s) or _GLYPH_TO_BUTTON.get(s.lower())
        if mapped in BUTTON_ALLOWLIST:
            return mapped
        titled = s[:1].upper() + s[1:] if s else ""
        if titled in BUTTON_ALLOWLIST:
            return titled
        upper = s.upper()
        if upper in BUTTON_ALLOWLIST:
            return upper
    return None


@dataclass(frozen=True)
class PictureHidTicket:
    ticket_id: str
    clock_ns: int
    frame_seq: int
    hid_button: str
    source: str = "gemini"
    model: str = "gemini-3.5-flash-lite"
    prompt_text: str | None = None
    visual_phase: str | None = None
    game_profile: str | None = None
    verb: str | None = None
    mode: str | None = None
    hid_domain: str = HidDomain.PICTURE.value
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def mint_picture_hid_ticket(
    *,
    clock_ns: int,
    frame_seq: int,
    hid_button: str | None,
    source: str = "gemini",
    model: str = "gemini-3.5-flash-lite",
    prompt_text: str | None = None,
    visual_phase: str | None = None,
    game_profile: str | None = None,
    verb: str | None = None,
    mode: str | None = None,
    game_state: str | None = "gameplay",
    glyph: str | None = None,
    session_id: str = "",
) -> PictureHidTicket:
    """Mint a seq-stamped picture HID ticket. Seeing-path + allowlist only."""
    normalized_source = normalize_source(source)
    if normalized_source not in PICTURE_HID_SOURCES or not is_picture_hid_source(source):
        raise PictureHidTicketSourceError(
            f"Cannot mint PictureHidTicket with source={source!r}. "
            f"Only seeing-path sources {PICTURE_HID_SOURCES} are allowed."
        )

    gst = str(game_state or "").strip().lower()
    if gst and gst != "gameplay":
        raise PictureHidTicketError(
            f"Cannot mint PictureHidTicket when game_state={game_state!r} (need gameplay)."
        )

    button = normalize_hid_button(hid_button, glyph=glyph)
    if not button:
        raise PictureHidTicketError(
            f"Cannot mint PictureHidTicket with hid_button={hid_button!r} glyph={glyph!r}."
        )

    seq = int(frame_seq)
    payload = {
        "v": DOMAIN,
        "session_id": str(session_id or ""),
        "clock_ns": int(clock_ns or 0),
        "frame_seq": seq,
        "hid_button": button,
        "source": normalized_source,
        "model": str(model or "gemini-3.5-flash-lite"),
        "prompt_text": (str(prompt_text).strip() or None) if prompt_text else None,
        "visual_phase": (str(visual_phase).strip() or None) if visual_phase else None,
        "game_profile": (str(game_profile).strip() or None) if game_profile else None,
        "verb": (str(verb).strip() or None) if verb else None,
        "mode": (str(mode).strip() or None) if mode else None,
        "hid_domain": HidDomain.PICTURE.value,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ticket_id = hashlib.sha256(raw).hexdigest()[:16]
    fields = {k: v for k, v in payload.items() if k != "v"}
    return PictureHidTicket(ticket_id=ticket_id, **fields)


def _lookup_verb_and_mode(
    *,
    hid_button: str,
    visual_context: dict[str, Any] | None,
    game_profile: str | None,
) -> tuple[str | None, str | None]:
    """EA verb from picture sheet + button. Fail-closed unlabeled."""
    ctx = dict(visual_context or {})
    if game_profile and not ctx.get("game_profile"):
        ctx["game_profile"] = game_profile
    gp = str(ctx.get("game_profile") or game_profile or "").lower()
    try:
        if "madden" in gp:
            from qoresence.observation.madden_controls import MaddenControlLookup

            lookup = MaddenControlLookup()
            mode = lookup.map_game_state_to_mode(ctx)
            return lookup.lookup_verb(hid_button, mode), mode
        if any(x in gp for x in ("cfb", "college", "ncaa")):
            from qoresence.observation.cfb_controls import CfbControlLookup

            lookup = CfbControlLookup()
            mode = lookup.map_game_state_to_mode(ctx)
            return lookup.lookup_verb(hid_button, mode), mode
    except Exception:
        return None, None
    return None, None


def visible_control_from_context(ctx: Any) -> dict[str, Any] | None:
    """Fail-closed visible_control dict from VisualContext or mapping."""
    if ctx is None:
        return None
    raw = None
    if isinstance(ctx, dict):
        raw = ctx.get("visible_control")
        if raw is None and isinstance(ctx.get("details"), dict):
            raw = ctx["details"].get("visible_control")
    else:
        raw = getattr(ctx, "visible_control", None)
        details = getattr(ctx, "details", None)
        if raw is None and isinstance(details, dict):
            raw = details.get("visible_control")
    if not isinstance(raw, dict):
        return None
    return raw


def try_mint_picture_hid_from_context(
    ctx: Any,
    *,
    frame_seq: int | None,
    clock_ns: int,
    source: str = "gemini",
    model: str = "gemini-3.5-flash-lite",
    session_id: str = "",
) -> PictureHidTicket | None:
    """Mint+store from VisualContext visible_control. None if unlabeled."""
    if frame_seq is None:
        return None
    try:
        seq = int(frame_seq)
    except (TypeError, ValueError):
        return None
    if seq <= 0:
        return None

    gst = ""
    profile = None
    phase = None
    vis_dict: dict[str, Any] | None = None
    if isinstance(ctx, dict):
        vis_dict = ctx
        gst = str(ctx.get("game_state") or "")
        profile = ctx.get("game_profile")
        phase = ctx.get("visual_phase")
        if phase is None and isinstance(ctx.get("details"), dict):
            phase = ctx["details"].get("visual_phase")
    elif ctx is not None:
        state = getattr(ctx, "game_state", None)
        gst = getattr(state, "value", state) if state is not None else ""
        gst = str(gst or "")
        profile = getattr(ctx, "game_profile", None)
        details = getattr(ctx, "details", None)
        if isinstance(details, dict):
            phase = details.get("visual_phase")
        if hasattr(ctx, "to_dict"):
            try:
                vis_dict = ctx.to_dict()
            except Exception:
                vis_dict = None

    vc = visible_control_from_context(ctx)
    if not vc:
        return None
    button_raw = vc.get("button")
    glyph = vc.get("glyph")
    prompt = vc.get("prompt")
    button = normalize_hid_button(button_raw, glyph=glyph)
    if not button:
        return None

    verb, mode = _lookup_verb_and_mode(
        hid_button=button,
        visual_context=vis_dict,
        game_profile=str(profile) if profile else None,
    )
    try:
        ticket = mint_picture_hid_ticket(
            clock_ns=int(clock_ns or 0),
            frame_seq=seq,
            hid_button=button,
            source=source,
            model=model,
            prompt_text=str(prompt).strip() if prompt else None,
            visual_phase=str(phase).strip() if phase else None,
            game_profile=str(profile).strip() if profile else None,
            verb=verb,
            mode=mode,
            game_state=gst or "gameplay",
            glyph=str(glyph) if glyph else None,
            session_id=session_id,
        )
    except (PictureHidTicketSourceError, PictureHidTicketError):
        return None

    try:
        from qoresence.sync.picture_hid_book import get_picture_hid_book

        get_picture_hid_book().put(ticket)
    except Exception:
        pass
    return ticket
