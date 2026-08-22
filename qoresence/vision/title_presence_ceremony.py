"""Live research-plane ceremony for title-presence observations.

Wrap dest is qoresence-research only. Optical records stay unmutated.
Ingredient sidecar is linked by source_hash, never rewritten into the record.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from qoresence.vision.title_presence_ingredient import append_ingredient, make_ingredient
from qoresence.vision.title_presence_wrap import (
    RESEARCH_DEST,
    OperatorGrant,
    WrapRefuse,
    append_wrap_envelope,
    envelope_to_dict,
    wrap_observation_for_plane,
)

ENV_GRANT_ID = "QORESENCE_WRAP_GRANT_ID"
ENV_GRANT_DEST = "QORESENCE_WRAP_GRANT_DEST"
ENV_GRANT_EXPIRES = "QORESENCE_WRAP_GRANT_EXPIRES_NS"
ENV_GRANT_TOKEN = "QORESENCE_WRAP_GRANT_TOKEN"
DEFAULT_GRANT_TTL_NS = 24 * 3600 * 10**9


def grant_from_env(now_ns: int | None = None) -> OperatorGrant | None:
    gid = os.environ.get(ENV_GRANT_ID, "").strip()
    if not gid:
        return None
    dest = os.environ.get(ENV_GRANT_DEST, RESEARCH_DEST).strip() or RESEARCH_DEST
    raw_exp = os.environ.get(ENV_GRANT_EXPIRES, "").strip()
    ts = int(now_ns if now_ns is not None else time.time_ns())
    try:
        expires = int(raw_exp) if raw_exp else ts + DEFAULT_GRANT_TTL_NS
    except ValueError:
        expires = ts + DEFAULT_GRANT_TTL_NS
    token = os.environ.get(ENV_GRANT_TOKEN, "").strip()
    return OperatorGrant(grant_id=gid, dest_plane=dest, expires_ns=expires, token=token)


def run_research_ceremony(
    record: dict[str, Any],
    *,
    dest_plane: str = RESEARCH_DEST,
    grant: OperatorGrant | None = None,
    ingredient_path: Path | str | None = None,
    wrap_path: Path | str | None = None,
    now_ns: int | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """Wrap a claimed observation onto qoresence-research and link an ingredient.

    Does not mutate `record`. Persistence is optional and sidecar-only.
    """
    ts = int(now_ns if now_ns is not None else time.time_ns())
    op_grant = grant if grant is not None else grant_from_env(ts)
    wrap = wrap_observation_for_plane(record, dest_plane, op_grant, now_ns=ts)
    if isinstance(wrap, WrapRefuse):
        return {
            "ok": False,
            "reason": wrap.reason,
            "dest_plane": dest_plane,
            "wrap": None,
            "ingredient": None,
        }
    ing = make_ingredient(record, created_ns=wrap.wrapped_at_ns)
    if ing is not None:
        ing["dest_plane"] = dest_plane
        ing["grant_id"] = wrap.grant_id
        ing["wrap_source_hash"] = wrap.source_hash
        if persist and ingredient_path:
            append_ingredient(Path(ingredient_path), ing)
    if persist and wrap_path:
        append_wrap_envelope(Path(wrap_path), wrap)
    return {
        "ok": True,
        "reason": "wrapped",
        "dest_plane": dest_plane,
        "wrap": envelope_to_dict(wrap),
        "ingredient": ing,
    }


def maybe_auto_wrap(
    record: dict[str, Any],
    *,
    wrap_path: Path | str | None = None,
    now_ns: int | None = None,
) -> dict[str, Any]:
    """No-op unless an operator grant is in the environment."""
    grant = grant_from_env(now_ns)
    if grant is None:
        return {"ok": False, "reason": "grant_missing", "wrap": None, "ingredient": None}
    return run_research_ceremony(
        record,
        dest_plane=grant.dest_plane or RESEARCH_DEST,
        grant=grant,
        wrap_path=wrap_path,
        now_ns=now_ns,
        persist=wrap_path is not None,
    )
