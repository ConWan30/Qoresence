"""Observation wire — adds play-pad observation to the Deck payload.

LAYER A: Spine isomorphism — observation object on the same clock as HDMI frame_seq.

Reads:
- hid_by_seq[frame_seq] for pad state aligned to HDMI frame
- visual_context for picture sheet (visual_phase → sheet mapper)
- Detects sheet conflict (picture sheet vs pad sheet)

Emits small observation dict:
{
    frame_seq: int,
    clock_ns: int,
    hid_button: str | null,
    verb: str | null,
    mode: str | null,
    visual_phase: str | null,
    game_profile: str | null,
    conflict: {picture_sheet, pad_sheet, kind, reason} | null
}

Unlabeled is the honest empty state (verb/mode/visual_phase/conflict may be null).
Never invents Snap Ball. Only emits when there's actual HID input at frame_seq.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def build_observation_wire(situation: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Build observation object for Deck wire from situation + hid_by_seq + visual_context.

    Args:
        situation: Current situation dict with frame_seq, game_profile, etc.

    Returns:
        Observation dict or None if no HID input at current frame_seq

    Observation schema:
        {
            frame_seq: int,
            clock_ns: int,
            hid_button: str | null,        # DualSense button name (e.g. "Cross")
            verb: str | null,               # EA verb (e.g. "Snap Ball") or null if unlabeled
            mode: str | null,               # Sheet key (e.g. "preplay_offense") or null
            visual_phase: str | null,       # Picture phase (e.g. "huddle_offense") or null
            game_profile: str | null,       # Game profile (e.g. "madden_27")
            conflict: {                     # Present when picture sheet != pad sheet
                picture_sheet: str,
                pad_sheet: str,
                kind: str,                  # "sheet_mismatch" | "lag" | "wrong_sheet"
                reason: str | null          # Optional detail (e.g. "syncLagMs=250ms")
            } | null
        }
    """
    if not isinstance(situation, dict):
        return None

    try:
        # Get frame_seq and clock_ns from situation
        frame_seq = situation.get("frame_seq")
        clock_ns = situation.get("clock_ns")
        if frame_seq is None:
            return None
        frame_seq = int(frame_seq)
        clock_ns = int(clock_ns or 0)

        # Get visual_context from VisualRuntime (live lobe context)
        visual_context_obj = None
        visual_context_dict: dict[str, Any] | None = None
        
        try:
            from qoresence.lobes.visual import get_last_visual_context
            
            visual_context_obj = get_last_visual_context()
            if visual_context_obj is not None:
                # Coerce VisualContext dataclass to dict for sheet_from_picture
                if hasattr(visual_context_obj, "to_dict"):
                    visual_context_dict = visual_context_obj.to_dict()
                elif isinstance(visual_context_obj, dict):
                    visual_context_dict = visual_context_obj
                elif hasattr(visual_context_obj, "__dict__"):
                    visual_context_dict = visual_context_obj.__dict__
        except Exception:
            pass

        # Extract visual_phase from visual_context (fail-closed)
        visual_phase = None
        if visual_context_dict:
            from qoresence.observation.sheet_from_picture import get_visual_phase_from_context

            visual_phase = get_visual_phase_from_context(visual_context_dict)
        
        # Get game_profile with fallback chain
        # 1. situation.game_profile (most reliable, from SituationModel)
        # 2. visual_context.game_profile
        # 3. profile_from_title(situation.game_title or visual_context.game_title)
        game_profile = situation.get("game_profile")
        if not game_profile and visual_context_dict:
            game_profile = visual_context_dict.get("game_profile")
        if not game_profile:
            # Try to infer from game_title
            game_title = situation.get("game_title")
            if not game_title and visual_context_dict:
                game_title = visual_context_dict.get("game_title")
            if game_title:
                title_lower = str(game_title).lower()
                if "madden" in title_lower:
                    game_profile = "madden_27"
                elif any(x in title_lower for x in ["college football", "ncaa", "cfb"]):
                    game_profile = "ncaa_football_27"

        # Determine which control lookup to use (Madden vs CFB)
        is_madden = False
        is_cfb = False
        if game_profile:
            gp = str(game_profile).lower()
            is_madden = "madden" in gp
            is_cfb = any(x in gp for x in ["cfb", "college", "ncaa"])

        # Observe button press(es) at frame_seq using appropriate controls
        observations: list[Any] = []
        if is_madden:
            from qoresence.observation.madden_controls import observe_button_press

            observations = observe_button_press(
                frame_seq=frame_seq,
                clock_ns=clock_ns,
                visual_context=visual_context_dict,
            )
        elif is_cfb:
            from qoresence.observation.cfb_controls import observe_button_press

            observations = observe_button_press(
                frame_seq=frame_seq,
                clock_ns=clock_ns,
                visual_context=visual_context_dict,
            )

        # Get HID button from hid_by_seq even if we don't have game profile
        # NEVER drop unlabeled observations - they are honest empty state
        hid_button = None
        verb = None
        mode = None
        
        if observations:
            # Take the first observation (most recent button press)
            obs = observations[0]
            hid_button = obs.hid_button
            verb = obs.verb
            mode = obs.mode
        else:
            # No game profile match OR no visual context for verb lookup
            # BUT: still check if there's HID input at this frame (unlabeled press)
            try:
                from qoresence.sync.hid_seq_line import get_sample
                
                sample = get_sample(frame_seq)
                if sample and sample.buttons:
                    # Unlabeled HID press: hid_button present, verb/mode None
                    hid_button = sample.buttons[0] if sample.buttons else None
            except Exception:
                pass
        
        # Return None only if NO HID input at all (not just unlabeled)
        if hid_button is None:
            return None

        # Detect sheet conflict (picture sheet vs pad sheet)
        conflict = None
        if visual_phase and mode:
            try:
                from qoresence.observation.sheet_conflict import detect_sheet_conflict
                from qoresence.observation.sheet_from_picture import map_visual_phase_to_sheet

                picture_sheet = map_visual_phase_to_sheet(visual_phase, game_profile)
                conflict_obj = detect_sheet_conflict(
                    frame_seq=frame_seq,
                    clock_ns=clock_ns,
                    hid_button=hid_button,
                    picture_sheet=picture_sheet,
                    pad_sheet=mode,
                    game_profile=game_profile,
                )
                if conflict_obj:
                    conflict = {
                        "picture_sheet": conflict_obj.picture_sheet,
                        "pad_sheet": conflict_obj.pad_sheet,
                        "kind": conflict_obj.kind,
                        "reason": conflict_obj.reason,
                    }
            except Exception as e:
                log.debug("Failed to detect sheet conflict: %s", e)

        # Build observation wire dict
        return {
            "frame_seq": frame_seq,
            "clock_ns": clock_ns,
            "hid_button": hid_button,
            "verb": verb,
            "mode": mode,
            "visual_phase": visual_phase,
            "game_profile": game_profile,
            "conflict": conflict,
        }

    except Exception as e:
        log.debug("Failed to build observation wire: %s", e)
        return None
