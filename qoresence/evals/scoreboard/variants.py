"""Eval variants — identical mechanics, different suspicion policy.

Every variant shares the stage-2 evidence floor: fresh, in-order, complete,
board-scene observations only. The only difference is what marks a transition
suspicious and therefore in need of corroboration:

- ``legacy``        pre-binding behavior: every parsed board exposes, no floor.
- ``baseline``      stage-2 floor, no transition suspicion (today's mint path).
- ``deterministic`` football-delta law marks suspicious transitions.
- ``typesafe``      cached Jev implausible-noul marks suspicious transitions
                    (falls back to the delta law when a row has no verdict).
- ``combined``      delta law OR Jev noul marks suspicious.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from qoresence.sync.digit_integrity import implausible_transition_reason
from qoresence.vision.score_recheck import BoardObservation, ScoreRecheck

VARIANT_NAMES = ("legacy", "baseline", "deterministic", "typesafe", "combined")

_JEV_SUSPICIOUS = 0.7

SuspicionFn = Callable[[BoardObservation, BoardObservation], bool]


def delta_suspicion(prior: BoardObservation, candidate: BoardObservation) -> bool:
    return implausible_transition_reason(*prior.pair, *candidate.pair) is not None


def never_suspicious(prior: BoardObservation, candidate: BoardObservation) -> bool:
    return False


def jev_verdicts_by_seq(observations: list[dict[str, Any]]) -> dict[int, float]:
    """frame_seq → implausible_noul for rows that carry a cached Jev verdict."""
    out: dict[int, float] = {}
    for row in observations:
        jev = row.get("jev") or {}
        noul = jev.get("implausible_noul")
        seq = row.get("frame_seq")
        if noul is None or seq is None:
            continue
        try:
            out[int(seq)] = float(noul)
        except (TypeError, ValueError):
            continue
    return out


def jev_suspicion(
    verdicts: dict[int, float],
    *,
    threshold: float = _JEV_SUSPICIOUS,
    fallback: SuspicionFn = delta_suspicion,
) -> SuspicionFn:
    """Suspicion from cached Jev nouls; rows without a verdict use ``fallback``."""

    def _suspect(prior: BoardObservation, candidate: BoardObservation) -> bool:
        noul = verdicts.get(candidate.frame_seq)
        if noul is None:
            return fallback(prior, candidate)
        return noul >= threshold

    return _suspect


def make_recheck(
    variant: str,
    observations: list[dict[str, Any]],
    *,
    jev_threshold: float = _JEV_SUSPICIOUS,
) -> ScoreRecheck:
    """One ScoreRecheck per variant; ``legacy`` is handled by the runner."""
    verdicts = jev_verdicts_by_seq(observations)
    if variant == "baseline":
        return ScoreRecheck(suspicion=never_suspicious)
    if variant == "deterministic":
        return ScoreRecheck()
    if variant == "typesafe":
        return ScoreRecheck(
            suspicion=jev_suspicion(verdicts, threshold=jev_threshold)
        )
    if variant == "combined":
        jev = jev_suspicion(
            verdicts, threshold=jev_threshold, fallback=never_suspicious
        )
        return ScoreRecheck(
            suspicion=lambda p, c: delta_suspicion(p, c) or jev(p, c)
        )
    raise ValueError(f"unknown recheck variant: {variant}")
