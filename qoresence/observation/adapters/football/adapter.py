"""FootballAdapter v0 — CFB and Madden share phases; profile honesty for HUD/blind spots."""

from __future__ import annotations

from copy import deepcopy

from qoresence.compose.clock_notary.envelope import SCHEMA

from .phases import (
    ACTIVE_PHASES,
    BOUNDARY_GAME_STATES,
    BOUNDARY_PHASES,
    MOMENT_BOUNDARY_TIMEOUT_NS,
    VALID_TRANSITIONS,
    VISUAL_PHASES,
)
from .profiles import blind_spots, hud_regions

POLICY_VERSION = "football-observation-1"
GAME_CATEGORY = "football"


class FootballAdapter:
    policy_version = POLICY_VERSION
    game_category = GAME_CATEGORY

    def accepts_category(self, category: str | None) -> bool:
        return category == GAME_CATEGORY

    def visual_phases(self) -> frozenset[str]:
        return VISUAL_PHASES

    def active_phases(self) -> frozenset[str]:
        return ACTIVE_PHASES

    def boundary_phases(self) -> frozenset[str]:
        return BOUNDARY_PHASES

    def boundary_game_states(self) -> frozenset[str]:
        return BOUNDARY_GAME_STATES

    def hud_regions(self, profile: str | None) -> dict[str, str]:
        return hud_regions(profile)

    def blind_spots(self, profile: str | None) -> tuple[str, ...]:
        return blind_spots(profile)

    def valid_transitions(self) -> dict[str, frozenset[str]]:
        return VALID_TRANSITIONS

    def moment_boundary_timeout_ns(self) -> int:
        return MOMENT_BOUNDARY_TIMEOUT_NS

    def input_availability(self, *, hid_observed: bool = False) -> str:
        if hid_observed:
            return "available"
        return "not_on_this_host"

    def should_open_moment(self, phase: str | None, record: dict | None) -> bool:
        return (
            phase in ACTIVE_PHASES
            and (record is None or record.get("end_ns") is not None)
        )

    def should_close_moment(
        self, phase: str | None, game_state: str | None
    ) -> bool:
        return phase in BOUNDARY_PHASES or (
            game_state is not None and game_state in BOUNDARY_GAME_STATES
        )

    def normalize_visual(self, event: dict) -> dict | None:
        from qoresence.observation.lifecycle import (
            event_replay_enabled,
            freeze_detector_output,
        )

        p = event.get("payload", {})
        if not self.accepts_category(p.get("game_category")):
            return None
        tick = p.get("observation_tick")
        eid = p.get("event_id")
        if (
            not isinstance(tick, dict)
            or not eid
            or tick.get("evidence_id") != eid
            or int(tick.get("clock_ns") or 0) != int(event.get("clock_ns") or 0)
        ):
            return None
        detector_output = None
        if isinstance(p.get("observation_detector_output"), dict):
            detector_output = deepcopy(p["observation_detector_output"])
        elif event_replay_enabled():
            detector_output = freeze_detector_output(p)
        phase = p.get("visual_phase")
        game_state = p.get("game_state")
        if isinstance(detector_output, dict):
            phase = detector_output.get("visual_phase") or phase
            game_state = detector_output.get("game_state") or game_state
        if phase is not None and phase not in VISUAL_PHASES:
            return None
        profile = p.get("game_profile") or p.get("profile")
        evidence = {
            "kind": "visual",
            "game_category": GAME_CATEGORY,
            "evidence_id": eid,
            "session_id": event["session_id"],
            "tick": deepcopy(tick),
            "phase": phase,
            "game_state": game_state,
            "game_profile": profile,
            "score_claim": p.get("observation_score_claim"),
            "model": p.get("model"),
            "frame_hash": p.get("frame_hash"),
        }
        if detector_output is not None:
            evidence["detector_output"] = detector_output
        return evidence

    def qualified_claim(self, evidence: dict) -> dict | None:
        from qoresence.observation.lifecycle import qualified_claim

        return qualified_claim(evidence)

    def new_candidate_record(
        self,
        event: dict,
        clock: int,
        evidence_id: str,
        policy_version: str,
    ) -> dict:
        from qoresence.observation.uncertainty import initial_uncertainty_channels

        input_availability = self.input_availability(hid_observed=False)
        return {
            "envelope_schema": SCHEMA,
            "policy_version": policy_version,
            "observation_id": evidence_id,
            "session_id": event["session_id"],
            "revision": 0,
            "kind": "candidate_football_play",
            "state": "candidate",
            "start_ns": clock,
            "end_ns": None,
            "last_clock_ns": clock,
            "input_availability": input_availability,
            "claims": [],
            "outcome": None,
            "uncertainty": ["inferred_visual_boundary", "input_unavailable"],
            "uncertainty_channels": initial_uncertainty_channels(input_availability),
            "ledger": [],
            "evidence_ids": [],
            "clip": {"status": "not_requested"},
        }


FOOTBALL_ADAPTER = FootballAdapter()
