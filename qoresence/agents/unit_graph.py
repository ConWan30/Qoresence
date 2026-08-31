"""Unit graph — directed control-flow with code gates.

Four node kinds: splitter, worker, code, gate.
A worker and its gate do not share a model context. The gate is code.
Loop lives inside a node (produce → check → correct) with cap 3.
Return the unit, not the batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from qoresence.vision.title_presence import PLANE as OBSERVATION_PLANE

UNIT_KINDS = frozenset({"splitter", "worker", "code", "gate"})
UNIT_SCOPES = frozenset({"chapter", "ticket"})
BATCH_SCOPES = frozenset({"drive", "batch"})
RETRY_CAP = 3


@dataclass
class Unit:
    """One bounded unit: one lobe, one chapter candidate, or one licensed act."""

    unit_id: str
    kind: str = "worker"
    scope: str = "chapter"
    claims_digits: bool = False
    source_ticket_id: str = ""
    expected_inputs: int | None = None
    actual_inputs: int | None = None
    is_freeze: bool = False
    freeze_kind: str = ""
    plane: str = OBSERVATION_PLANE
    payload: dict[str, Any] = field(default_factory=dict)
    node_kind: str = ""
    retries: int = 0


@dataclass(frozen=True)
class CheckResult:
    """Code-gate result. Empty errors is not a pass unless checks actually ran."""

    ok: bool
    errors: tuple[str, ...]
    checks_run: int

    @property
    def passed(self) -> bool:
        return bool(self.ok) and self.checks_run > 0 and not self.errors


@dataclass(frozen=True)
class CorrectionReceipt:
    unit_id: str
    errors: tuple[str, ...]
    attempts: int
    correction_exhausted: bool = False


@dataclass(frozen=True)
class CorrectionOutcome:
    kept: tuple[Unit, ...]
    receipts: tuple[CorrectionReceipt, ...]


def evaluate_unit(unit: Unit) -> CheckResult:
    """Program-evaluable gate. Must be able to fail while nobody is watching."""
    errors: list[str] = []
    checks = 0

    checks += 1
    if str(unit.plane or "") != OBSERVATION_PLANE:
        errors.append("plane_not_observation")

    checks += 1
    scope = str(unit.scope or "")
    if scope in BATCH_SCOPES or scope not in UNIT_SCOPES:
        errors.append("batch_scope")

    if unit.claims_digits:
        checks += 1
        if not str(unit.source_ticket_id or "").strip():
            errors.append("digits_without_seeing_path_mint")

    if unit.expected_inputs is not None:
        checks += 1
        actual = unit.actual_inputs if unit.actual_inputs is not None else 0
        if int(actual) != int(unit.expected_inputs):
            errors.append("merge_count_gap")

    if unit.is_freeze or str(unit.node_kind or "").upper() == "FREEZE":
        checks += 1
        if not str(unit.freeze_kind or "").strip():
            errors.append("freeze_missing_kind")

    ok = (not errors) and checks > 0
    return CheckResult(ok=ok, errors=tuple(errors), checks_run=checks)


def correct_units(units: list[Unit] | tuple[Unit, ...]) -> CorrectionOutcome:
    """Drop a failed unit only. Siblings stay. Retry cap 3, then exhausted.

    No model call to 'fix' the unit. Re-check the same unit; after cap, drop it.
    """
    kept: list[Unit] = []
    receipts: list[CorrectionReceipt] = []
    for unit in units:
        result: CheckResult | None = None
        attempts = 0
        while attempts < RETRY_CAP:
            attempts += 1
            unit.retries = attempts
            result = evaluate_unit(unit)
            if result.passed:
                kept.append(unit)
                break
        else:
            errs = result.errors if result is not None else ("unevaluated",)
            receipts.append(
                CorrectionReceipt(
                    unit_id=unit.unit_id,
                    errors=errs,
                    attempts=attempts,
                    correction_exhausted=True,
                )
            )
    return CorrectionOutcome(kept=tuple(kept), receipts=tuple(receipts))


def units_from_chapter_nodes(nodes: list[Any]) -> list[Unit]:
    """Map DriveGraph chapter candidates to units (one node → one unit)."""
    out: list[Unit] = []
    for i, n in enumerate(nodes):
        kind = str(getattr(n, "kind", "") or "")
        payload = getattr(n, "payload", None)
        payload_d = dict(payload) if isinstance(payload, dict) else {}
        ticket = str(payload_d.get("ticket_id") or payload_d.get("source_ticket_id") or "")
        claims = any(k in payload_d for k in ("home_score", "away_score", "score"))
        freeze = kind.upper() == "FREEZE" or "FREEZE" in (payload_d.get("flags") or [])
        out.append(
            Unit(
                unit_id=str(getattr(n, "node_id", "") or f"chapter:{i}"),
                kind="worker",
                scope="chapter",
                claims_digits=claims,
                source_ticket_id=ticket,
                is_freeze=bool(freeze),
                freeze_kind=str(payload_d.get("freeze_kind") or ""),
                plane=str(payload_d.get("plane") or OBSERVATION_PLANE),
                payload=payload_d,
                node_kind=kind,
            )
        )
    return out
