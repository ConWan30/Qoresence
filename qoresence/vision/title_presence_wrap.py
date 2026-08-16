"""Fail-closed re-wrap ceremony for title-presence observations.

Interface is live; composition is not. Default allowlist is empty.
Never mutates the source record. Never writes a truth-plane store.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from qoresence.vision.title_presence import PLANE, record_valid, source_hash

DEST_ALLOWLIST_DEFAULT: frozenset[str] = frozenset()


@dataclass(frozen=True)
class OperatorGrant:
    grant_id: str
    dest_plane: str
    expires_ns: int
    token: str = ""


@dataclass(frozen=True)
class WrapRefuse:
    ok: bool = False
    reason: str = "refused"


@dataclass(frozen=True)
class WrapEnvelope:
    ok: bool = True
    plane: str = ""
    source_plane: str = PLANE
    source_hash: str = ""
    wrapped_at_ns: int = 0
    grant_id: str = ""


def wrap_observation_for_plane(
    record: dict[str, Any],
    dest_plane: str,
    operator_grant: OperatorGrant | None = None,
    *,
    allowlist: frozenset[str] | set[str] | None = None,
    now_ns: int | None = None,
) -> WrapRefuse | WrapEnvelope:
    """Fail-closed wrap. Empty allowlist → always refuse dest."""
    allowed = DEST_ALLOWLIST_DEFAULT if allowlist is None else frozenset(allowlist)
    if not record_valid(record):
        return WrapRefuse(reason="plane_mismatch")
    dest = str(dest_plane or "").strip()
    if not dest or dest == PLANE:
        return WrapRefuse(reason="dest_invalid")
    if dest not in allowed:
        return WrapRefuse(reason="dest_not_allowlisted")
    if not record.get("claim"):
        return WrapRefuse(reason="no_claim")
    if operator_grant is None:
        return WrapRefuse(reason="grant_missing")
    if str(operator_grant.dest_plane) != dest:
        return WrapRefuse(reason="grant_dest_mismatch")
    ts = int(now_ns if now_ns is not None else time.time_ns())
    if int(operator_grant.expires_ns) <= ts:
        return WrapRefuse(reason="grant_expired")
    if not str(operator_grant.grant_id or "").strip():
        return WrapRefuse(reason="grant_id_missing")
    # Structural: new envelope only. Source plane stays on the original record.
    return WrapEnvelope(
        plane=dest,
        source_plane=PLANE,
        source_hash=source_hash(record),
        wrapped_at_ns=ts,
        grant_id=str(operator_grant.grant_id),
    )
