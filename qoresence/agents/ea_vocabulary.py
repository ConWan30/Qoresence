"""EA vocabulary for ClutchBot lines — real-time named clutch only.

Reads hid_by_seq[frame_seq] + visual_phase to get the EA dictionary verb
(Snap Ball, Stiff Arm, Throw Ball Away, Hit Stick, ...) at the clutch frame.

GATE: only on licensed clutch/trajectory moments. If unlabeled (verb/mode is None)
or not a clutch moment → returns None. Never invents plays from pad.

Real time: verb is from the clutch frame, not a later button.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def get_ea_vocabulary_at_frame(
    frame_seq: int,
    clock_ns: int,
    visual_context: dict[str, Any] | None = None,
    game_profile: str | None = None,
) -> str | None:
    """Get EA dictionary verb from hid_by_seq at frame_seq (fail-closed).

    Args:
        frame_seq: Frame sequence number (FrameHub seq) at clutch moment
        clock_ns: Frame clock_ns
        visual_context: Visual context payload with visual_phase
        game_profile: Game profile id (e.g. "madden_27", "ncaa_football_27")

    Returns:
        EA verb string (e.g. "Snap Ball", "Stiff Arm") or None if unlabeled

    Fail-closed: returns None if:
    - No HID sample at frame_seq
    - No visual_context or no visual_phase (unlabeled)
    - Mode is None (cannot map to sheet)
    - Game profile is wrong
    """
    if not visual_context or frame_seq <= 0:
        return None

    try:
        # Determine game (Madden vs CFB)
        is_madden = False
        is_cfb = False
        if game_profile:
            gp = str(game_profile).lower()
            is_madden = "madden" in gp
            is_cfb = any(x in gp for x in ["cfb", "college", "ncaa"])

        if not is_madden and not is_cfb:
            return None

        # Get observations at frame_seq
        observations: list[Any] = []
        if is_madden:
            from qoresence.observation.madden_controls import observe_button_press

            observations = observe_button_press(
                frame_seq=frame_seq,
                clock_ns=clock_ns,
                visual_context=visual_context,
            )
        elif is_cfb:
            from qoresence.observation.cfb_controls import observe_button_press

            observations = observe_button_press(
                frame_seq=frame_seq,
                clock_ns=clock_ns,
                visual_context=visual_context,
            )

        if not observations:
            return None

        # Take the first observation (most recent button press)
        obs = observations[0]
        return obs.verb if obs.verb else None

    except Exception as e:
        log.debug("get_ea_vocabulary_at_frame failed: %s", e)
        return None


def enrich_clutch_line(
    base_message: str,
    frame_seq: int,
    clock_ns: int,
    visual_context: dict[str, Any] | None = None,
    game_profile: str | None = None,
) -> str:
    """Add EA vocabulary to clutch line when present (fail-closed).

    Args:
        base_message: Base soft chat message (e.g. "Clutch window opening")
        frame_seq: Frame sequence at clutch moment
        clock_ns: Frame clock_ns
        visual_context: Visual context payload
        game_profile: Game profile id

    Returns:
        Enriched message with EA verb if present, otherwise unchanged

    Examples:
        "Clutch window opening" → "Clutch window opening — Snap Ball"
        "Red-zone energy spike" → "Red-zone energy spike — Stiff Arm"
        (unlabeled) → base_message unchanged
    """
    verb = get_ea_vocabulary_at_frame(
        frame_seq=frame_seq,
        clock_ns=clock_ns,
        visual_context=visual_context,
        game_profile=game_profile,
    )

    if verb:
        return f"{base_message} — {verb}"
    return base_message
