"""Two glyphs. Observation cannot promote Truth."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LockState(StrEnum):
    DARK = "DARK"
    OBS = "OBS"
    TRUTH = "TRUTH"


ICE = "#4FE0D4"
PHOSPHOR = "#C6F26A"
INK = "#e8f2ec"
VOID = "#0b0f0d"


@dataclass(frozen=True)
class DualLocks:
    observation: LockState
    truth: LockState

    @property
    def obs_glyph(self) -> str:
        return "OBS" if self.observation is LockState.OBS else "\u25a1"

    @property
    def truth_glyph(self) -> str:
        return "TRUTH" if self.truth is LockState.TRUTH else "\u25a1"

    @property
    def obs_color(self) -> str:
        return ICE if self.observation is LockState.OBS else VOID

    @property
    def truth_color(self) -> str:
        return PHOSPHOR if self.truth is LockState.TRUTH else VOID

    def to_hud(self) -> dict:
        return {
            "obs": {
                "glyph": self.obs_glyph,
                "state": self.observation.value,
                "color": self.obs_color,
                "plane": "observation",
            },
            "truth": {
                "glyph": self.truth_glyph,
                "state": self.truth.value,
                "color": self.truth_color,
                "plane": "truth",
            },
            "claim": "coupling / receipt pointers only — not humanity",
        }


def observation_lock(*, coupling_ticket: bool, same_seq: bool) -> LockState:
    if coupling_ticket and same_seq:
        return LockState.OBS
    return LockState.DARK


def truth_lock(*, consent_granted: bool, wrap_sealed: bool) -> LockState:
    if consent_granted and wrap_sealed:
        return LockState.TRUTH
    return LockState.DARK


def compose_locks(
    *,
    coupling_ticket: bool,
    same_seq: bool,
    consent_granted: bool,
    wrap_sealed: bool,
) -> DualLocks:
    obs = observation_lock(coupling_ticket=coupling_ticket, same_seq=same_seq)
    truth = truth_lock(consent_granted=consent_granted, wrap_sealed=wrap_sealed)
    if obs is LockState.OBS and not (consent_granted and wrap_sealed):
        truth = LockState.DARK
    return DualLocks(observation=obs, truth=truth)
