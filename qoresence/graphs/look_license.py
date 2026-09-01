"""LookLicense — receipt that names the next look, never a score.

Observation plane only. Append-only JSONL under logs/pilot.
Score-digit keys and frozen-field markers refuse the write.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from qoresence.agents.learning_constraint import (
    CONSTRAINT_KINDS,
    FROZEN_FIELD_MARKERS,
    from_accepted_confirm,
)
from qoresence.vision.confirm_ticket import SCORE_PAIR
from qoresence.vision.title_presence import PLANE as OBSERVATION_PLANE

log = logging.getLogger(__name__)

DEFAULT_LICENSE_LOG = Path("logs/pilot/look_licenses.jsonl")
PATH_ENV = "QORESENCE_LOOK_LICENSES_PATH"

GRAPH_NAMES = frozenset(
    {
        "ticket_provenance",
        "crop_evidence",
        "same_seq_join",
        "refuse_chain",
        "scale_stack",
        "negative_evidence",
    }
)

LOOK_KINDS = frozenset(
    {
        "mint",
        "reuse",
        "remint",
        "refuse",
        "crop_prefer",
        "crop_fallback",
        "crop_pause",
        "join_ok",
        "seq_skew",
        "slack_hold",
        "plane_dim",
        "mint_blocked",
        "schedule_skip",
        "pause_crops_only",
        "tick_peek",
        "phrase_coupling",
        "drive_confirm",
        "session_wrap",
        "scale_refuse",
        "skip_look",
        "no_claim",
    }
)

PERMIT_FIELDS = frozenset(
    {
        "next_action",
        "crop_role",
        "crop_index",
        "keep_crop",
        "reuse_identity",
        "frame_seq",
        "scale",
        "look",
        "constraint_kind",
        "unit_kind",
        "freeze_kind",
        "crop",
        "profile",
        "weight",
    }
)

_SCORE_KEYS = frozenset({"home_score", "away_score", "home", "away", "score"})


@dataclass(frozen=True)
class LookLicense:
    id: str
    clock_ns: int
    session_id: str
    graph: str
    kind: str
    permits: dict[str, Any] = field(default_factory=dict)
    refuses: tuple[str, ...] = ()
    source_ticket_id: str = ""
    frame_seq: int | None = None
    crop_hash: str = ""
    plane: str = OBSERVATION_PLANE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def make_license(
    *,
    graph: str,
    kind: str,
    session_id: str = "",
    clock_ns: int | None = None,
    permits: dict[str, Any] | None = None,
    refuses: list[str] | tuple[str, ...] | None = None,
    source_ticket_id: str = "",
    frame_seq: int | None = None,
    crop_hash: str = "",
) -> LookLicense | None:
    """Build a LookLicense or None if refused.

    Missing graph/kind, score-digit payload, and frozen-field writes return None.
    """
    g = str(graph or "").strip()
    k = str(kind or "").strip()
    if g not in GRAPH_NAMES or k not in LOOK_KINDS:
        return None
    body = dict(permits or {})
    extra = {x: body[x] for x in list(body) if x not in PERMIT_FIELDS}
    if extra:
        return None
    if _has_score_digits(body) or _frozen_field_write(body, refuses):
        return None
    ck = str(body.get("constraint_kind") or "").strip()
    if ck and ck not in CONSTRAINT_KINDS:
        return None
    ns = int(clock_ns) if clock_ns is not None else int(time.monotonic_ns())
    refused = tuple(str(x) for x in (refuses or ()) if str(x).strip())
    lid = _license_id(g, k, ns, body, refused)
    return LookLicense(
        id=lid,
        clock_ns=ns,
        session_id=str(session_id or ""),
        graph=g,
        kind=k,
        permits=body,
        refuses=refused,
        source_ticket_id=str(source_ticket_id or ""),
        frame_seq=int(frame_seq) if frame_seq is not None else None,
        crop_hash=str(crop_hash or ""),
        plane=OBSERVATION_PLANE,
    )


def license_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    envp = os.environ.get(PATH_ENV, "").strip()
    if envp:
        return Path(envp)
    return DEFAULT_LICENSE_LOG


def append_license(
    license: LookLicense,
    path: Path | str | None = None,
) -> Path | None:
    """Append one license as JSONL. Never rewrites the file. Never emits bus events."""
    dest = license_path(path)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(license.to_dict(), separators=(",", ":"), sort_keys=True) + "\n")
        return dest
    except Exception as e:
        log.debug("look license append skipped: %s", e)
        return None


def load_licenses(path: Path | str | None = None) -> list[LookLicense]:
    dest = license_path(path)
    if not dest.is_file():
        return []
    out: list[LookLicense] = []
    try:
        text = dest.read_text(encoding="utf-8")
    except Exception:
        return []
    for line in text.splitlines():
        if not line.strip():
            continue
        rec = parse_license_record(line)
        if rec is not None:
            out.append(rec)
    return out


def parse_license_record(raw: str | dict[str, Any]) -> LookLicense | None:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return None
    else:
        data = dict(raw)
    if not isinstance(data, dict):
        return None
    permits = data.get("permits") if isinstance(data.get("permits"), dict) else {}
    refuses = data.get("refuses") if isinstance(data.get("refuses"), (list, tuple)) else ()
    frame_seq = data.get("frame_seq")
    try:
        fs = int(frame_seq) if frame_seq is not None else None
    except (TypeError, ValueError):
        fs = None
    return make_license(
        graph=str(data.get("graph") or ""),
        kind=str(data.get("kind") or ""),
        session_id=str(data.get("session_id") or ""),
        clock_ns=int(data.get("clock_ns") or 0),
        permits=dict(permits),
        refuses=tuple(refuses),
        source_ticket_id=str(data.get("source_ticket_id") or ""),
        frame_seq=fs,
        crop_hash=str(data.get("crop_hash") or ""),
    )


def maybe_constraint_from_license(
    license: LookLicense | None,
    *,
    ticket: Any | None = None,
    drive_id: str = "",
) -> Any | None:
    """Mint an existing LearningConstraint kind when both flags are on.

    Graphs do not add new constraint kinds. Missing ticket / illegal payload → None.
    """
    if license is None:
        return None
    try:
        from qoresence.agents.learning_edge import enabled as learning_on
        from qoresence.graphs.flags import enabled as look_on

        if not look_on() or not learning_on():
            return None
    except Exception:
        return None
    kind = str(license.permits.get("constraint_kind") or "").strip()
    if not kind or kind not in CONSTRAINT_KINDS:
        return None
    ticket_id = str(license.source_ticket_id or "").strip()
    if ticket is None and not ticket_id:
        return None
    payload = {
        k: v
        for k, v in license.permits.items()
        if k in {"crop", "profile", "unit_kind", "freeze_kind", "constraint_kind"}
        or k in {"threshold", "stability_count", "window", "weight", "min_coupling"}
    }
    if kind == "crop_band" and "crop" not in payload:
        return None
    if kind == "schedule_skip" and "unit_kind" not in payload:
        payload["unit_kind"] = payload.get("unit_kind") or "confirm"
    if kind == "freeze_weight" and ("freeze_kind" not in payload or "weight" not in payload):
        return None
    constraint = from_accepted_confirm(
        ticket,
        source_ticket_id=ticket_id,
        kind=kind,
        payload=payload,
        evidence={"frame_seq": license.frame_seq} if license.frame_seq is not None else None,
        session_id=license.session_id,
        drive_id=drive_id,
        created_clock_ns=license.clock_ns,
    )
    return constraint


def _walk_strings(obj: Any) -> list[str]:
    if obj is None:
        return []
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        bits: list[str] = []
        for k, v in obj.items():
            bits.append(str(k))
            bits.extend(_walk_strings(v))
        return bits
    if isinstance(obj, (list, tuple)):
        bits: list[str] = []
        for v in obj:
            bits.extend(_walk_strings(v))
        return bits
    return [str(obj)]


def _has_score_digits(data: dict[str, Any]) -> bool:
    for key in data:
        if str(key).lower() in _SCORE_KEYS:
            return True
    blob = " ".join(_walk_strings(data))
    if SCORE_PAIR.search(blob):
        return True
    import re

    return bool(re.search(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b", blob))


def _frozen_field_write(
    permits: dict[str, Any],
    refuses: list[str] | tuple[str, ...] | None,
) -> bool:
    blob = f"{' '.join(_walk_strings(permits))} {' '.join(_walk_strings(list(refuses or ())))}".lower()
    return any(m in blob for m in FROZEN_FIELD_MARKERS)


def _license_id(
    graph: str,
    kind: str,
    clock_ns: int,
    permits: dict[str, Any],
    refuses: tuple[str, ...],
) -> str:
    raw = json.dumps(
        {
            "graph": graph,
            "kind": kind,
            "clock_ns": int(clock_ns),
            "permits": permits,
            "refuses": list(refuses),
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
