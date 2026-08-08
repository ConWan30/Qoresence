"""Router must-fire predicates and decision logging (Trio Principle 2).

The router is the sole mechanism for regulating A2A invocation cost.
Must-fire predicates override the utility-cost trade-off for
safety-critical or high-value events.

This module formalizes the previously scattered ``if`` branches in
the orchestrator into a typed predicate set, and provides a
``RouterDecision`` log entry for every evaluation (fire or suppress).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# ROUTER DECISION LOG
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class RouterDecision:
    """A single router evaluation — fire or suppress.

    Emitted for every router check, not just fires, enabling
    offline analysis of what triggered or suppressed reasoning.
    """

    fired: bool
    reason: str
    must_fire_hit: str | None = None  # which predicate forced the fire
    inputs: dict[str, Any] = field(default_factory=dict)
    interval_s: float = 0.0
    last_trigger_age_s: float = 0.0
    clock_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ──────────────────────────────────────────────────────────────────────────────
# MUST-FIRE PREDICATE PROTOCOL
# ──────────────────────────────────────────────────────────────────────────────


class MustFirePredicate(Protocol):
    """A predicate that forces A2A invocation regardless of cost.

    Each predicate checks the situation dict and returns True if
    the reasoning tier must be invoked. The predicate also provides
    a ``name`` attribute for logging.
    """

    name: str

    def check(self, situation: dict[str, Any]) -> bool: ...


# ──────────────────────────────────────────────────────────────────────────────
# BUILT-IN PREDICATES
# ──────────────────────────────────────────────────────────────────────────────


class _BigPlayPredicate:
    """Fire on big-play outcome events (touchdown, turnover, etc.)."""

    name = "big_play"

    BIG_PLAY_EVENTS: frozenset[str] = frozenset({
        "touchdown", "field_goal", "safety", "two_point_conversion",
        "turnover", "score_changed",
    })

    def check(self, situation: dict[str, Any]) -> bool:
        last_event = str(situation.get("last_outcome_event") or "").lower()
        return last_event in self.BIG_PLAY_EVENTS


class _TwoMinuteWarningPredicate:
    """Fire on two-minute warning event."""

    name = "two_minute_warning"

    def check(self, situation: dict[str, Any]) -> bool:
        last_event = str(situation.get("last_outcome_event") or "").lower()
        return last_event == "two_minute_warning"


class _RedZonePredicate:
    """Fire on red zone entry."""

    name = "red_zone_entry"

    def check(self, situation: dict[str, Any]) -> bool:
        last_event = str(situation.get("last_outcome_event") or "").lower()
        return last_event == "red_zone_entry"


class _ShooterKillStreakPredicate:
    """Fire on shooter kill streaks (3+ kills in 5s)."""

    name = "shooter_kill_streak"

    def check(self, situation: dict[str, Any]) -> bool:
        cat = str(situation.get("game_category") or "").lower()
        if cat not in {"shooter", "fps"}:
            return False
        triggers = situation.get("controller_triggers_5s") or 0
        kills = situation.get("kills") or 0
        # High trigger activity suggests combat intensity
        return int(triggers) >= 10 or int(kills) > 0


class _OperatorQueryPredicate:
    """Fire when an operator query is pending (force=True)."""

    name = "operator_query"

    def check(self, situation: dict[str, Any]) -> bool:
        return bool(situation.get("_force") or situation.get("force"))


# ──────────────────────────────────────────────────────────────────────────────
# PREDICATE REGISTRY
# ──────────────────────────────────────────────────────────────────────────────


# Default predicates for each game category
_FOOTBALL_PREDICATES: list[MustFirePredicate] = [
    _BigPlayPredicate(),
    _TwoMinuteWarningPredicate(),
    _RedZonePredicate(),
    _OperatorQueryPredicate(),
]

_SHOOTER_PREDICATES: list[MustFirePredicate] = [
    _ShooterKillStreakPredicate(),
    _OperatorQueryPredicate(),
]

_ALL_PREDICATES: list[MustFirePredicate] = [
    _BigPlayPredicate(),
    _TwoMinuteWarningPredicate(),
    _RedZonePredicate(),
    _ShooterKillStreakPredicate(),
    _OperatorQueryPredicate(),
]


def get_predicates_for_category(category: str) -> list[MustFirePredicate]:
    """Return the must-fire predicates for a game category."""
    cat = (category or "").lower()
    if cat in {"football", "ncaa_football", "ncaa"}:
        return list(_FOOTBALL_PREDICATES)
    if cat in {"shooter", "fps"}:
        return list(_SHOOTER_PREDICATES)
    # Unknown category: use all predicates (safe default)
    return list(_ALL_PREDICATES)


# ──────────────────────────────────────────────────────────────────────────────
# ROUTER EVALUATION
# ──────────────────────────────────────────────────────────────────────────────


def evaluate_must_fire(
    situation: dict[str, Any],
    predicates: list[MustFirePredicate] | None = None,
) -> tuple[bool, str | None]:
    """Evaluate must-fire predicates against the situation.

    Returns (fired, predicate_name). If any predicate fires, returns
    (True, predicate_name). Otherwise returns (False, None).
    """
    if predicates is None:
        cat = str(situation.get("game_category") or "")
        predicates = get_predicates_for_category(cat)

    for pred in predicates:
        try:
            if pred.check(situation):
                return True, pred.name
        except Exception as e:
            log.debug("Must-fire predicate %s errored: %s", pred.name, e)
    return False, None


def build_router_decision(
    *,
    fired: bool,
    reason: str,
    situation: dict[str, Any],
    must_fire_hit: str | None = None,
    interval_s: float = 0.0,
    last_trigger_age_s: float = 0.0,
) -> RouterDecision:
    """Build a RouterDecision log entry."""
    # Extract key inputs for logging (avoid dumping the entire situation)
    inputs = {
        "game_category": situation.get("game_category"),
        "game_state": situation.get("game_state"),
        "last_outcome_event": situation.get("last_outcome_event"),
        "coupling": situation.get("coupling"),
        "drive_phase": situation.get("drive_phase"),
        "visual_confidence": situation.get("visual_confidence"),
    }
    return RouterDecision(
        fired=fired,
        reason=reason,
        must_fire_hit=must_fire_hit,
        inputs=inputs,
        interval_s=interval_s,
        last_trigger_age_s=last_trigger_age_s,
        clock_ns=time.monotonic_ns(),
    )
