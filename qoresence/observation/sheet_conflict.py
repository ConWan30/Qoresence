"""Observation-plane conflict detection (Layer 3).

Detects when the picture sheet (visual_phase → sheet) and the pad-named sheet
disagree. Emits an observation conflict, not a play claim.

Example: visual_phase=running (sheet: running) but labeled observation would be
"Snap Ball" (sheet: preplay_offense) → that is sheet_mismatch or lag, never
"they snapped during a run."

Conflict reasons:
- sheet_mismatch: Picture and pad sheets differ (honest disagreement)
- lag: syncLagMs / pll signals indicate input/video desync (when available)
- wrong_sheet: Catch-all when reason cannot be determined

No conflict when:
- Sheets match (picture and pad agree)
- Unlabeled pad (no visual_phase) → nothing to disagree with
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SheetConflict:
    """Observation conflict when picture sheet and pad sheet disagree."""

    frame_seq: int
    clock_ns: int
    hid_button: str  # DualSense button name
    picture_sheet: str  # Sheet from visual_phase (picture language)
    pad_sheet: str  # Sheet from button verb (pad language)
    game_profile: str
    kind: str = "sheet_mismatch"  # sheet_mismatch | lag | wrong_sheet
    reason: str | None = None  # Optional detail (e.g. "syncLagMs=250ms")
    source: str = "observation_conflict"

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_seq": self.frame_seq,
            "clock_ns": self.clock_ns,
            "hid_button": self.hid_button,
            "picture_sheet": self.picture_sheet,
            "pad_sheet": self.pad_sheet,
            "game_profile": self.game_profile,
            "kind": self.kind,
            "reason": self.reason,
            "source": self.source,
        }


def detect_sheet_conflict(
    frame_seq: int,
    clock_ns: int,
    hid_button: str,
    picture_sheet: str | None,
    pad_sheet: str | None,
    game_profile: str | None = None,
) -> SheetConflict | None:
    """Detect observation conflict when picture and pad sheets disagree.

    Args:
        frame_seq: Frame sequence number
        clock_ns: Frame clock_ns
        hid_button: DualSense button name (e.g. "Cross")
        picture_sheet: Sheet from visual_phase (e.g. "running")
        pad_sheet: Sheet from button verb (e.g. "preplay_offense")
        game_profile: Game profile id (e.g. "madden_27")

    Returns:
        SheetConflict if sheets disagree, None if they match or no conflict

    No conflict when:
    - picture_sheet is None (no visual_phase → unlabeled)
    - pad_sheet is None (no verb → unlabeled)
    - picture_sheet == pad_sheet (sheets match)
    """
    # No conflict if either sheet is None (unlabeled)
    if picture_sheet is None or pad_sheet is None:
        return None

    # No conflict if sheets match
    if picture_sheet == pad_sheet:
        return None

    # Sheets disagree → emit conflict
    # Try to determine reason (lag vs wrong_sheet)
    kind = "sheet_mismatch"
    reason = None

    # Check for sync lag signals (if available)
    try:
        from qoresence.sync.ivc import get_last_coupling

        coupling = get_last_coupling()
        if coupling:
            sync_lag_ms = coupling.get("syncLagMs")
            pll_lock = coupling.get("pll_lock")
            if sync_lag_ms is not None and abs(float(sync_lag_ms)) > 50:
                kind = "lag"
                reason = f"syncLagMs={sync_lag_ms}ms"
            elif pll_lock is not None and not pll_lock:
                kind = "lag"
                reason = "pll_unlock"
    except Exception:
        # syncLagMs / pll not available → use generic sheet_mismatch
        pass

    return SheetConflict(
        frame_seq=frame_seq,
        clock_ns=clock_ns,
        hid_button=hid_button,
        picture_sheet=picture_sheet,
        pad_sheet=pad_sheet,
        game_profile=game_profile or "",
        kind=kind,
        reason=reason,
    )


def check_observation_conflict(
    observation: dict[str, Any],
    visual_context: dict[str, Any] | None = None,
) -> SheetConflict | None:
    """Check if an observation conflicts with visual_context picture sheet.

    Args:
        observation: Observation dict with {frame_seq, clock_ns, hid_button, mode, ...}
        visual_context: Visual context payload with visual_phase

    Returns:
        SheetConflict if sheets disagree, None otherwise
    """
    if not observation:
        return None

    frame_seq = int(observation.get("frame_seq") or 0)
    clock_ns = int(observation.get("clock_ns") or 0)
    hid_button = str(observation.get("hid_button") or "")
    pad_sheet = observation.get("mode")  # Sheet from observation (pad language)
    game_profile = observation.get("game_profile")

    # Get picture sheet from visual_context
    picture_sheet = None
    if visual_context:
        from qoresence.observation.sheet_from_picture import map_context_to_sheet

        picture_sheet = map_context_to_sheet(visual_context)

    return detect_sheet_conflict(
        frame_seq=frame_seq,
        clock_ns=clock_ns,
        hid_button=hid_button,
        picture_sheet=picture_sheet,
        pad_sheet=pad_sheet,
        game_profile=game_profile,
    )
