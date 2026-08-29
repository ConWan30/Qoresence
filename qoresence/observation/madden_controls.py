"""Madden 27 PlayStation control verb lookup — observation plane only.

Maps DualSense button presses to their purpose in the active Madden 27 mode.
Uses EA official PlayStation controls from
https://www.ea.com/games/madden-nfl/madden-nfl-27/controls-hub/playstation-controls-hub

Architecture:
- Reads hid_by_seq[frame_seq] for pad state aligned to HDMI frame
- Maps visual_context.game_state to one of 10 Madden modes (fail-closed)
- Returns verb(s) for the active button(s) in that mode
- Never invents plays from analog/phrase
- Emits small observation events: {frame_seq, clock_ns, hid, verb, mode, source, plane}
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PLANE = "qoresence-observation"

# DualSense button names (internal mask → name)
# Must match qoresence/sync/hid_report.py
BUTTON_NAMES = {
    1 << 0: "Cross",
    1 << 1: "Circle",
    1 << 2: "Square",
    1 << 3: "Triangle",
    1 << 4: "L1",
    1 << 5: "R1",
    1 << 6: "L2",
    1 << 7: "R2",
    1 << 8: "CREATE",
    1 << 9: "OPTIONS",
    1 << 10: "L3",
    1 << 11: "R3",
}


@dataclass(frozen=True)
class ControlObservation:
    """One button press observation aligned to HDMI frame."""

    frame_seq: int
    clock_ns: int
    hid_button: str  # DualSense button name (e.g. "Cross")
    verb: str | None  # EA verb(s) for this button in active mode, or None if mode unknown
    mode: str | None  # Madden mode key (e.g. "preplay_offense") or None if unknown
    source: str = "ea_ps_controls_hub"

    def to_dict(self) -> dict[str, Any]:
        return {
            "plane": PLANE,
            "frame_seq": self.frame_seq,
            "clock_ns": self.clock_ns,
            "hid_button": self.hid_button,
            "verb": self.verb,
            "mode": self.mode,
            "source": self.source,
        }


class MaddenControlLookup:
    """Madden 27 control legend. Fail-closed mode detection."""

    def __init__(self) -> None:
        self._controls: dict[str, dict[str, list[str]]] = {}
        self._load_controls()

    def _load_controls(self) -> None:
        """Load EA Madden 27 controls from data file."""
        try:
            data_file = Path(__file__).parent.parent / "profiles" / "madden_27_controls_ps.json"
            with open(data_file, encoding="utf-8") as f:
                data = json.load(f)
            self._controls = data.get("modes", {})
        except Exception as e:
            log.warning("Failed to load Madden 27 controls: %s", e)
            self._controls = {}

    def lookup_verb(self, button: str, mode: str | None) -> str | None:
        """Return verb(s) for button in mode, or None if mode unknown.

        Args:
            button: DualSense button name (e.g. "Cross")
            mode: Madden mode key (e.g. "preplay_offense") or None

        Returns:
            Comma-separated verb string if found, else None
        """
        if mode is None or mode not in self._controls:
            return None
        mode_controls = self._controls[mode]
        verbs = mode_controls.get(button)
        if not verbs:
            return None
        return ", ".join(verbs) if isinstance(verbs, list) else str(verbs)

    def map_game_state_to_mode(self, visual_context: dict[str, Any]) -> str | None:
        """Map visual_context to one of the 10 Madden modes (fail-closed).

        Fail-closed: unknown/missing phase, wrong title, or non-gameplay → None.
        """
        game_state = visual_context.get("game_state") or ""
        if not game_state:
            details = visual_context.get("details")
            if isinstance(details, dict):
                game_state = str(details.get("game_state") or "")
        game_profile = visual_context.get("game_profile", "") or ""

        if "madden" not in str(game_profile).lower():
            return None

        if game_state != "gameplay":
            return None

        from qoresence.observation.sheet_from_picture import map_context_to_sheet

        return map_context_to_sheet(visual_context)


_lookup: MaddenControlLookup | None = None


def get_madden_lookup() -> MaddenControlLookup:
    """Process-wide cached legend — JSON load stays off the grab thread."""
    global _lookup
    if _lookup is None:
        _lookup = MaddenControlLookup()
    return _lookup


def observe_button_press(
    *,
    frame_seq: int,
    clock_ns: int,
    visual_context: dict[str, Any] | None = None,
) -> list[ControlObservation]:
    """Observe button press(es) from hid_by_seq at frame_seq.

    Returns a list of ControlObservation for each active button (may be empty).
    Missing sheet / phase keeps verb and mode None (unlabeled).
    """
    observations: list[ControlObservation] = []
    try:
        from qoresence.sync.hid_seq_line import get_sample

        sample = get_sample(frame_seq)
        if sample is None:
            return observations

        lookup = get_madden_lookup()
        mode = lookup.map_game_state_to_mode(visual_context or {}) if visual_context else None

        active_buttons = list(sample.buttons) if sample.buttons else []

        for btn_name in active_buttons:
            verb = lookup.lookup_verb(btn_name, mode)
            observations.append(
                ControlObservation(
                    frame_seq=frame_seq,
                    clock_ns=clock_ns,
                    hid_button=btn_name,
                    verb=verb,
                    mode=mode,
                )
            )

    except Exception as e:
        log.debug("observe_button_press failed: %s", e)

    return observations


def observe_hid_edge(
    *,
    frame_seq: int,
    clock_ns: int,
    button_name: str,
    visual_context: dict[str, Any] | None = None,
) -> ControlObservation:
    """Observe a single HID edge (press/release) at frame_seq."""
    lookup = get_madden_lookup()
    mode = lookup.map_game_state_to_mode(visual_context or {}) if visual_context else None
    verb = lookup.lookup_verb(button_name, mode)
    return ControlObservation(
        frame_seq=frame_seq,
        clock_ns=clock_ns,
        hid_button=button_name,
        verb=verb,
        mode=mode,
    )
