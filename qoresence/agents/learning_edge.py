"""Learning edge — next-run splitter constraints from accepted confirms.

Default OFF. --play does not enable this. When off, do not read or write
the constraint store; DriveGraph and crop bands stay as on main.

The learning edge does not carry prose and does not rewrite worker prompts.
It lands on the splitter: crop band, hysteresis, rank weight, try_open,
schedule skip, freeze weight.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from qoresence.agents.learning_constraint import (
    CONSTRAINT_KINDS,
    DEFAULT_CONSTRAINT_LOG,
    LearningConstraint,
    append_constraint,
    from_accepted_confirm,
    load_constraints,
)
from qoresence.agents.unit_graph import correct_units, units_from_chapter_nodes
from qoresence.vision.confirm_ticket import ConfirmTicket

log = logging.getLogger(__name__)

ENV_NAME = "QORESENCE_LEARNING_EDGE"
MAX_RANK_DELTA = 2.0
DEFAULT_MIN_COUPLING = 0.55

_applied_ids: tuple[str, ...] = ()
_config_on = False


def set_config_enabled(value: bool) -> None:
    """CLI/config latch. Tests should prefer QORESENCE_LEARNING_EDGE."""
    global _config_on
    _config_on = bool(value)


def enabled(config: Any | None = None) -> bool:
    env = os.environ.get(ENV_NAME, "").strip().lower() in {"1", "true", "yes", "on"}
    cfg = bool(getattr(config, "learning_edge", False)) if config is not None else _config_on
    return bool(env or cfg)


def reset_applied() -> None:
    global _applied_ids, _config_on
    _applied_ids = ()
    _config_on = False


def closeout_applied() -> list[str] | None:
    """Non-breaking closeout key. None when flag off (omit the field)."""
    if not enabled():
        return None
    return list(_applied_ids)


@dataclass
class SplitterInputs:
    profile: str = ""
    crops: tuple[tuple[float, float, float, float], ...] = ()
    rank_weights: dict[str, float] = field(default_factory=dict)
    min_coupling_to_open: float = DEFAULT_MIN_COUPLING
    hysteresis: dict[str, Any] = field(default_factory=dict)
    schedule_skip: frozenset[str] = field(default_factory=frozenset)
    freeze_weights: dict[str, float] = field(default_factory=dict)
    applied_ids: tuple[str, ...] = ()


def _constraint_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    envp = os.environ.get("QORESENCE_LEARNING_CONSTRAINTS_PATH", "").strip()
    if envp:
        return Path(envp)
    return DEFAULT_CONSTRAINT_LOG


def load_applicable(
    profile: str = "",
    path: Path | str | None = None,
    *,
    config: Any | None = None,
) -> list[LearningConstraint]:
    if not enabled(config):
        return []
    dest = _constraint_path(path)
    out: list[LearningConstraint] = []
    for c in load_constraints(dest):
        if not str(c.source_ticket_id or "").strip():
            log.info("learning-edge skip ticketless constraint id=%s", c.id)
            continue
        if c.kind not in CONSTRAINT_KINDS:
            log.info("learning-edge skip unknown kind=%s id=%s", c.kind, c.id)
            continue
        if c.frozen:
            log.info("learning-edge skip frozen id=%s", c.id)
            continue
        if not _profile_ok(c, profile):
            continue
        out.append(c)
    return out


def apply_constraints(
    inputs: SplitterInputs,
    constraints: list[LearningConstraint] | tuple[LearningConstraint, ...],
    *,
    config: Any | None = None,
) -> SplitterInputs:
    """Apply allowed kinds to splitter inputs. Flag off → inputs unchanged."""
    global _applied_ids
    if not enabled(config):
        _applied_ids = ()
        return inputs
    crops = list(inputs.crops)
    rank_weights = dict(inputs.rank_weights)
    hyst = dict(inputs.hysteresis)
    skip: set[str] = set(inputs.schedule_skip)
    freeze_w = dict(inputs.freeze_weights)
    coupling = float(inputs.min_coupling_to_open)
    applied: list[str] = []
    for c in constraints:
        if not str(c.source_ticket_id or "").strip():
            continue
        if c.kind not in CONSTRAINT_KINDS or c.frozen:
            log.info("learning-edge skip kind=%s frozen=%s id=%s", c.kind, c.frozen, c.id)
            continue
        payload = c.payload or {}
        if c.kind == "crop_band":
            band = payload.get("crop")
            if isinstance(band, (list, tuple)) and len(band) == 4:
                try:
                    t = (float(band[0]), float(band[1]), float(band[2]), float(band[3]))
                except (TypeError, ValueError):
                    continue
                rest = [b for b in crops if b != t]
                crops = [t, *rest]
                applied.append(c.id)
        elif c.kind == "hysteresis":
            for k in ("threshold", "stability_count", "window"):
                if k in payload:
                    hyst[k] = payload[k]
            applied.append(c.id)
        elif c.kind == "rank_weight":
            node_kind = str(payload.get("node_kind") or payload.get("kind") or "")
            try:
                delta = float(payload.get("weight") or 0.0)
            except (TypeError, ValueError):
                continue
            if node_kind:
                rank_weights[node_kind] = max(-MAX_RANK_DELTA, min(MAX_RANK_DELTA, delta))
                applied.append(c.id)
        elif c.kind == "try_open":
            raw = payload.get("min_coupling", payload.get("threshold"))
            try:
                coupling = float(raw)
            except (TypeError, ValueError):
                continue
            applied.append(c.id)
        elif c.kind == "schedule_skip":
            unit_kind = str(payload.get("unit_kind") or payload.get("node_kind") or "")
            if unit_kind:
                skip.add(unit_kind)
                applied.append(c.id)
        elif c.kind == "freeze_weight":
            fk = str(payload.get("freeze_kind") or "")
            try:
                w = float(payload.get("weight") or 0.0)
            except (TypeError, ValueError):
                continue
            if fk:
                freeze_w[fk] = w
                applied.append(c.id)
    _applied_ids = tuple(applied)
    return replace(
        inputs,
        crops=tuple(crops),
        rank_weights=rank_weights,
        min_coupling_to_open=coupling,
        hysteresis=hyst,
        schedule_skip=frozenset(skip),
        freeze_weights=freeze_w,
        applied_ids=tuple(applied),
    )


def overlay_crops(
    profile: str | object | None,
    base: tuple[tuple[float, float, float, float], ...],
    *,
    path: Path | str | None = None,
    config: Any | None = None,
) -> tuple[tuple[float, float, float, float], ...] | None:
    """Return overlay crops when flag on and a crop_band applies; else None."""
    if not enabled(config):
        return None
    cons = load_applicable(str(profile or ""), path=path, config=config)
    inputs = SplitterInputs(profile=str(profile or ""), crops=base)
    out = apply_constraints(inputs, cons, config=config)
    if not out.applied_ids or out.crops == base:
        return None
    return out.crops


def split_chapter_units(
    graph: Any,
    *,
    k: int = 8,
    config: Any | None = None,
    constraints: list[LearningConstraint] | None = None,
) -> tuple[list[Any], CorrectionOutcomeLite]:
    """Splitter: rank chapters, optionally skip/correct. Flag off = ranked_chapter_nodes."""
    nodes = list(graph.ranked_chapter_nodes(k=k))
    look_skip = _look_schedule_skip()
    if not enabled(config):
        if look_skip:
            nodes = [n for n in nodes if n.kind not in look_skip]
        return nodes, CorrectionOutcomeLite(kept_ids=tuple(n.node_id for n in nodes), receipts=())
    cons = constraints if constraints is not None else load_applicable(config=config)
    dummy = apply_constraints(SplitterInputs(), cons, config=config)
    skip = set(dummy.schedule_skip) | look_skip
    if skip:
        nodes = [n for n in nodes if n.kind not in skip]
    units = units_from_chapter_nodes(nodes)
    outcome = correct_units(units)
    kept_ids = {u.unit_id for u in outcome.kept}
    kept_nodes = [n for n in nodes if n.node_id in kept_ids]
    receipts = tuple(
        {"unit_id": r.unit_id, "errors": list(r.errors), "correction_exhausted": r.correction_exhausted}
        for r in outcome.receipts
    )
    return kept_nodes, CorrectionOutcomeLite(
        kept_ids=tuple(n.node_id for n in kept_nodes), receipts=receipts
    )


@dataclass(frozen=True)
class CorrectionOutcomeLite:
    kept_ids: tuple[str, ...]
    receipts: tuple[dict[str, Any], ...]


def maybe_record_on_resolve(
    *,
    ticket: ConfirmTicket | None,
    profile: str = "",
    crop: list[float] | tuple[float, ...] | None = None,
    frame_seq: int | None = None,
    drive_id: str = "",
    session_id: str = "",
    path: Path | str | None = None,
    config: Any | None = None,
) -> LearningConstraint | None:
    """Write a crop_band constraint after an accepted confirm. No-op when flag off."""
    if not enabled(config):
        return None
    if ticket is None:
        return None
    evidence: dict[str, Any] = {}
    if crop is not None:
        evidence["crop"] = list(crop)
    if frame_seq is not None:
        evidence["frame_seq"] = frame_seq
    if profile:
        evidence["profile"] = profile
    constraint = from_accepted_confirm(
        ticket,
        kind="crop_band" if crop is not None else None,
        payload={"profile": profile} if profile else None,
        evidence=evidence or None,
        session_id=session_id or ticket.session_id,
        drive_id=drive_id,
    )
    if constraint is None:
        return None
    append_constraint(constraint, path=_constraint_path(path))
    return constraint


def _look_schedule_skip() -> set[str]:
    """Look-graph refuse skip, when --look-graphs is on. Empty when off."""
    try:
        from qoresence.graphs.flags import graph_enabled
        from qoresence.graphs.refuse_chain import schedule_skip_unit

        if not graph_enabled("refuse_chain"):
            return set()
        raw = str(schedule_skip_unit() or "").strip()
        if raw == "confirm":
            return {"confirm", "confirm_score"}
        if raw:
            return {raw}
    except Exception:
        return set()
    return set()


def _profile_ok(constraint: LearningConstraint, live_profile: str) -> bool:
    marked = str((constraint.payload or {}).get("profile") or "")
    if not marked or not live_profile:
        return True
    try:
        from qoresence.vision.scorebug_crops import is_madden_profile

        return is_madden_profile(marked) == is_madden_profile(live_profile)
    except Exception:
        return marked.lower() in live_profile.lower() or live_profile.lower() in marked.lower()
