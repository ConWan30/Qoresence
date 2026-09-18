from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from qoresence.sync.digit_integrity import (
    CONFIRM_DIGIT_MAX_AGE_NS,
    implausible_transition_reason,
)

# Scenes where no reliable board observation exists (mirrors the extractor's
# _LOADING_STATES). Menu/pause/results still paint the match score, so they
# stay admissible; an empty scene (unset game_state) is admissible too.
_NON_BOARD_SCENES = frozenset({"loading", "cutscene", "intro", "replay"})


@dataclass(frozen=True)
class BoardObservation:
    session_id: str
    frame_seq: int
    captured_ns: int
    crop_hash: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int
    scene: str = "gameplay"
    quarter: int | None = None
    game_clock: str | None = None

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.session_id, self.home_team.upper(), self.away_team.upper()

    @property
    def pair(self) -> tuple[int, int]:
        return self.home_score, self.away_score


class ScoreRecheck:
    def __init__(
        self,
        *,
        gap_ns: int = 30_000_000_000,
        max_rechecks: int = 2,
        suspicion: Any = None,
    ):
        self.gap_ns = gap_ns
        self.max_rechecks = max_rechecks
        # suspicion(prior, candidate) -> bool. Default: the football-delta law.
        # Eval variants inject Jev-derived suspicion on identical mechanics.
        self._suspicion = suspicion
        self.accepted: BoardObservation | None = None
        self.pending: BoardObservation | None = None
        self.latest: BoardObservation | None = None
        self.attempts = 0
        self.started_ns = 0

    def _is_suspicious(self, prior: BoardObservation, candidate: BoardObservation) -> bool:
        if self._suspicion is not None:
            return bool(self._suspicion(prior, candidate))
        return (
            implausible_transition_reason(*prior.pair, *candidate.pair) is not None
        )

    def evaluate(self, candidate: BoardObservation, now_ns: int) -> str:
        if (
            not all((candidate.session_id, candidate.home_team, candidate.away_team,
                     candidate.crop_hash))
            or candidate.frame_seq <= 0 or candidate.captured_ns <= 0
            or type(candidate.home_score) is not int or type(candidate.away_score) is not int
            or not (0 <= candidate.home_score <= 99 and 0 <= candidate.away_score <= 99)
        ):
            return "missing_evidence"
        if not 0 <= now_ns - candidate.captured_ns <= CONFIRM_DIGIT_MAX_AGE_NS:
            return "stale"
        if str(candidate.scene or "").lower() in _NON_BOARD_SCENES:
            return "scene_unknown"
        latest = self.latest
        if latest is not None and latest.session_id == candidate.session_id:
            if candidate.frame_seq == latest.frame_seq:
                return "duplicate"
            if candidate.frame_seq < latest.frame_seq or candidate.captured_ns <= latest.captured_ns:
                return "out_of_order"
        self.latest = candidate
        prior = self.accepted
        if (
            prior is None or prior.identity != candidate.identity
            or candidate.captured_ns - prior.captured_ns > self.gap_ns
            or not self._is_suspicious(prior, candidate)
        ):
            return self._accept(candidate)
        if self.pending is None:
            self.pending = candidate
            self.started_ns = now_ns
            self.attempts = 0
            return "recheck"
        if now_ns - self.started_ns > self.gap_ns or self.attempts >= self.max_rechecks:
            return "exhausted"
        self.attempts += 1
        if self.pending.identity == candidate.identity and self.pending.pair == candidate.pair:
            return self._accept(candidate)
        self.pending = candidate
        return "exhausted" if self.attempts >= self.max_rechecks else "recheck"

    def _accept(self, candidate: BoardObservation) -> str:
        self.accepted = candidate
        self.pending = None
        self.attempts = 0
        self.started_ns = 0
        return "accepted"
