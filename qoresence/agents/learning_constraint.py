"""Typed learning constraints from accepted seeing-path confirms.

Observation plane only. Append-only JSONL under logs/pilot.
Default unused — the splitter does not read this store (P4 wires --learning-edge).

A constraint is not a report: it names a splitter field the next run may read.
Score digits, wrap dests, and other frozen fields are refused here.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from qoresence.vision.confirm_ticket import SCORE_PAIR, ConfirmTicket
from qoresence.vision.title_presence import PLANE as OBSERVATION_PLANE

log = logging.getLogger(__name__)

DEFAULT_CONSTRAINT_LOG = Path("logs/pilot/learning_constraints.jsonl")

CONSTRAINT_KINDS = frozenset(
    {
        "crop_band",
        "hysteresis",
        "rank_weight",
        "try_open",
        "schedule_skip",
        "freeze_weight",
    }
)

KIND_TARGETS: dict[str, str] = {
    "crop_band": "scorebug_crops",
    "hysteresis": "title_presence.hysteresis",
    "rank_weight": "drive_graph.rank_weight",
    "try_open": "prediction.min_coupling_to_open",
    "schedule_skip": "splitter.schedule_skip",
    "freeze_weight": "pilot.freeze_weight",
}

# Writable kinds are never frozen. A write that names these markers is refused.
FROZEN_FIELD_MARKERS = (
    "home_score",
    "away_score",
    "score_digit",
    "qortroller-truth",
    "wrap_dest",
    "mid-drive",
    "publish",
    "twitch",
    "humanity",
    "eligibility",
    "anti-cheat",
    "confidence_gate",
    "capture_owner",
    "dshow",
)

_SCORE_KEYS = frozenset({"home_score", "away_score", "home", "away", "score"})
_CROP_KEYS = frozenset({"crop", "crops", "band", "bands"})


@dataclass
class LearningConstraint:
    """One append-only splitter constraint derived from a seeing-path mint."""

    id: str
    created_clock_ns: int
    session_id: str
    drive_id: str
    source_ticket_id: str
    kind: str
    target: str
    payload: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    frozen: bool = False
    plane: str = OBSERVATION_PLANE

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def from_accepted_confirm(
    ticket: ConfirmTicket | None = None,
    *,
    source_ticket_id: str = "",
    kind: str | None = None,
    target: str = "",
    payload: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    session_id: str = "",
    drive_id: str = "",
    created_clock_ns: int | None = None,
) -> LearningConstraint | None:
    """Build a constraint from an accepted confirm, or None if refused.

    Missing seeing-path ticket id, unknown kind, score-digit payload, and
    frozen-field writes all return None. Absence of an error string is not
    a pass — callers must check for None.
    """
    payload = dict(payload or {})
    evidence = dict(evidence or {})
    ticket_id = _ticket_id(ticket, source_ticket_id)
    if not ticket_id:
        return None

    inferred = _infer_kind(kind, payload, evidence)
    if inferred is None or inferred not in CONSTRAINT_KINDS:
        return None

    if _has_score_digits(payload) or _has_score_digits(evidence):
        return None
    if _frozen_field_write(target, payload, evidence):
        return None
    if not _payload_ok_for_kind(inferred, payload, evidence):
        return None

    resolved_target = str(target or KIND_TARGETS[inferred]).strip()
    if not resolved_target:
        return None
    if _frozen_field_write(resolved_target, {}, {}):
        return None

    clock_ns = int(created_clock_ns) if created_clock_ns is not None else _clock_ns(ticket)
    sid = str(session_id or (ticket.session_id if ticket is not None else "") or "")
    crop_payload = _normalize_crop_payload(inferred, payload, evidence)
    body = crop_payload if inferred == "crop_band" else dict(payload)
    evid = _sanitize_evidence(evidence)

    cid = _constraint_id(ticket_id, inferred, resolved_target, clock_ns, body)
    return LearningConstraint(
        id=cid,
        created_clock_ns=clock_ns,
        session_id=sid,
        drive_id=str(drive_id or ""),
        source_ticket_id=ticket_id,
        kind=inferred,
        target=resolved_target,
        payload=body,
        evidence=evid,
        frozen=False,
        plane=OBSERVATION_PLANE,
    )


def append_constraint(
    constraint: LearningConstraint,
    path: Path | str | None = None,
) -> Path | None:
    """Append one constraint as JSONL. Never rewrites the file."""
    dest = Path(path) if path is not None else DEFAULT_CONSTRAINT_LOG
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as f:
            f.write(json.dumps(constraint.to_dict(), separators=(",", ":"), sort_keys=True) + "\n")
        return dest
    except Exception as e:
        log.debug("learning constraint append skipped: %s", e)
        return None


def load_constraints(path: Path | str | None = None) -> list[LearningConstraint]:
    """Read append-only JSONL. Skip corrupt / refused records."""
    dest = Path(path) if path is not None else DEFAULT_CONSTRAINT_LOG
    if not dest.is_file():
        return []
    out: list[LearningConstraint] = []
    try:
        text = dest.read_text(encoding="utf-8")
    except Exception:
        return []
    for line in text.splitlines():
        if not line.strip():
            continue
        rec = parse_constraint_record(line)
        if rec is not None:
            out.append(rec)
    return out


def parse_constraint_record(raw: str | dict[str, Any]) -> LearningConstraint | None:
    """Re-validate a stored dict/JSON line. Ticketless or illegal records drop."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception:
            return None
    else:
        data = dict(raw)
    if not isinstance(data, dict):
        return None
    ticket_id = str(data.get("source_ticket_id") or "").strip()
    kind = str(data.get("kind") or "").strip()
    if not ticket_id or kind not in CONSTRAINT_KINDS:
        return None
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    evidence = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    if _has_score_digits(payload) or _has_score_digits(evidence):
        return None
    if _frozen_field_write(str(data.get("target") or ""), payload, evidence):
        return None
    plane = str(data.get("plane") or OBSERVATION_PLANE)
    if plane != OBSERVATION_PLANE:
        return None
    try:
        clock_ns = int(data.get("created_clock_ns") or 0)
    except (TypeError, ValueError):
        return None
    cid = str(data.get("id") or "").strip()
    if not cid:
        return None
    return LearningConstraint(
        id=cid,
        created_clock_ns=clock_ns,
        session_id=str(data.get("session_id") or ""),
        drive_id=str(data.get("drive_id") or ""),
        source_ticket_id=ticket_id,
        kind=kind,
        target=str(data.get("target") or KIND_TARGETS.get(kind, "")),
        payload=dict(payload),
        evidence=dict(evidence),
        frozen=False,
        plane=OBSERVATION_PLANE,
    )


def _ticket_id(ticket: ConfirmTicket | None, explicit: str) -> str:
    if ticket is not None:
        return str(ticket.ticket_id or "").strip()
    return str(explicit or "").strip()


def _clock_ns(ticket: ConfirmTicket | None) -> int:
    if ticket is not None:
        try:
            return int(ticket.clock_ns or 0)
        except (TypeError, ValueError):
            pass
    return int(time.monotonic_ns())


def _infer_kind(
    kind: str | None,
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> str | None:
    raw = str(kind or "").strip()
    if raw:
        return raw
    if _crop_from(payload) is not None or _crop_from(evidence) is not None:
        return "crop_band"
    return None


def _crop_from(data: dict[str, Any]) -> list[float] | None:
    band = data.get("crop") if "crop" in data else data.get("band")
    if band is None and "crops" in data:
        crops = data.get("crops")
        if isinstance(crops, (list, tuple)) and crops:
            band = crops[0]
    if band is None and "bands" in data:
        bands = data.get("bands")
        if isinstance(bands, (list, tuple)) and bands:
            band = bands[0]
    return _as_crop(band)


def _as_crop(band: Any) -> list[float] | None:
    if not isinstance(band, (list, tuple)) or len(band) != 4:
        return None
    try:
        x1, x2, y1, y2 = (float(band[0]), float(band[1]), float(band[2]), float(band[3]))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        return None
    return [x1, x2, y1, y2]


def _payload_ok_for_kind(
    kind: str,
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    if kind == "crop_band":
        return _crop_from(payload) is not None or _crop_from(evidence) is not None
    if kind == "hysteresis":
        return "threshold" in payload or "stability_count" in payload or "window" in payload
    if kind == "rank_weight":
        return "weight" in payload and ("node_kind" in payload or "kind" in payload)
    if kind == "try_open":
        return "min_coupling" in payload or "threshold" in payload
    if kind == "schedule_skip":
        return bool(payload.get("unit_kind") or payload.get("node_kind") or payload.get("unit_id"))
    if kind == "freeze_weight":
        return "freeze_kind" in payload and "weight" in payload
    return False


def _normalize_crop_payload(
    kind: str,
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    if kind != "crop_band":
        return dict(payload)
    crop = _crop_from(payload) or _crop_from(evidence)
    out: dict[str, Any] = {}
    if crop is not None:
        out["crop"] = crop
    profile = payload.get("profile") or evidence.get("profile")
    if profile:
        out["profile"] = str(profile)
    for k, v in payload.items():
        if k in _CROP_KEYS or k == "profile":
            continue
        out[k] = v
    return out


def _sanitize_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    keep = ("frame_seq", "lock", "climax", "freeze_kind", "profile", "crop", "crops", "band")
    out: dict[str, Any] = {}
    for k in keep:
        if k in evidence and evidence[k] is not None:
            out[k] = evidence[k]
    return out


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
    return bool(re.search(r"\b\d{1,2}\s*[-–—:]\s*\d{1,2}\b", blob))


def _frozen_field_write(
    target: str,
    payload: dict[str, Any],
    evidence: dict[str, Any],
) -> bool:
    blob = f"{target} {' '.join(_walk_strings(payload))} {' '.join(_walk_strings(evidence))}".lower()
    return any(m in blob for m in FROZEN_FIELD_MARKERS)


def _constraint_id(
    ticket_id: str,
    kind: str,
    target: str,
    clock_ns: int,
    payload: dict[str, Any],
) -> str:
    raw = json.dumps(
        {
            "ticket": ticket_id,
            "kind": kind,
            "target": target,
            "clock_ns": int(clock_ns),
            "payload": payload,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]
