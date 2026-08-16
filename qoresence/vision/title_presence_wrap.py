"""Fail-closed re-wrap ceremony for title-presence observations.

Live dest is qoresence-research only. Truth-plane dests are denied.
Never mutates the source record. Never writes a truth-plane store.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from qoresence.vision.title_presence import PLANE, record_valid, source_hash

RESEARCH_DEST = "qoresence-research"
DEST_ALLOWLIST_DEFAULT: frozenset[str] = frozenset({RESEARCH_DEST})
DEST_DENYLIST: frozenset[str] = frozenset(
    {"qortroller-truth", "qortroller", "vapi-truth", "poac", "poep"}
)


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


def dest_denied(dest_plane: str) -> bool:
    dest = str(dest_plane or "").strip().lower()
    if not dest:
        return False
    if dest in DEST_DENYLIST:
        return True
    if "qortroller" in dest or "poac" in dest or dest.endswith("-truth"):
        return True
    return False


def wrap_observation_for_plane(
    record: dict[str, Any],
    dest_plane: str,
    operator_grant: OperatorGrant | None = None,
    *,
    allowlist: frozenset[str] | set[str] | None = None,
    now_ns: int | None = None,
) -> WrapRefuse | WrapEnvelope:
    """Fail-closed wrap. Default dest allowlist is qoresence-research."""
    allowed = DEST_ALLOWLIST_DEFAULT if allowlist is None else frozenset(allowlist)
    if not record_valid(record):
        return WrapRefuse(reason="plane_mismatch")
    dest = str(dest_plane or "").strip()
    if not dest or dest == PLANE:
        return WrapRefuse(reason="dest_invalid")
    if dest_denied(dest):
        return WrapRefuse(reason="dest_denied")
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


def envelope_to_dict(env: WrapEnvelope) -> dict[str, Any]:
    return {
        "ok": True,
        "plane": env.plane,
        "source_plane": env.source_plane,
        "source_hash": env.source_hash,
        "wrapped_at_ns": env.wrapped_at_ns,
        "grant_id": env.grant_id,
    }


def append_wrap_envelope(path: Path, envelope: WrapEnvelope) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(envelope_to_dict(envelope), sort_keys=True) + "\n")
