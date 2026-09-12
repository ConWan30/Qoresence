"""Game observation adapter protocol — sport/title rules stay out of the reducer."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class GameObservationAdapter(Protocol):
    """Boundary, HUD, and outcome rules for one game family."""

    policy_version: str
    game_category: str

    def accepts_category(self, category: str | None) -> bool:
        """Return True only when this adapter owns the category."""
        ...

    def visual_phases(self) -> frozenset[str]:
        """Picture-language phases the detector may emit."""
        ...

    def active_phases(self) -> frozenset[str]:
        """Phases that may open a candidate moment."""
        ...

    def boundary_phases(self) -> frozenset[str]:
        """Phases that close an open moment."""
        ...

    def boundary_game_states(self) -> frozenset[str]:
        """Non-play game states that close an open moment."""
        ...

    def hud_regions(self, profile: str | None) -> dict[str, str]:
        """Named HUD regions for scorebug / clock / down-distance (observation only)."""
        ...

    def blind_spots(self, profile: str | None) -> tuple[str, ...]:
        """Known limits — honest CFB vs Madden where they differ."""
        ...

    def valid_transitions(self) -> dict[str, frozenset[str]]:
        """Allowed visual_phase transitions (detector-time, not frame-exact)."""
        ...

    def moment_boundary_timeout_ns(self) -> int:
        """Open interval timeout before unresolved closure."""
        ...

    def input_availability(self, *, hid_observed: bool = False) -> str:
        """HID join state — never invent presses."""
        ...

    def should_open_moment(self, phase: str | None, record: dict | None) -> bool:
        """Whether an active phase should start a new candidate."""
        ...

    def should_close_moment(
        self, phase: str | None, game_state: str | None
    ) -> bool:
        """Whether the current interval should provisionally close."""
        ...

    def normalize_visual(self, event: dict) -> dict | None:
        """Map a bus visual_context dict to normalized evidence, or abstain."""
        ...

    def qualified_claim(self, evidence: dict) -> dict | None:
        """Fail-closed scoreboard qualification from frozen evidence."""
        ...

    def new_candidate_record(
        self,
        event: dict,
        clock: int,
        evidence_id: str,
        policy_version: str,
    ) -> dict:
        """Shape for a new candidate observation record."""
        ...
