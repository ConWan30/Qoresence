"""TruthFact model + canonical hashing (``qoresence.truth.fact.v0``).

Canonical JSON matches ``compose/clock_notary/envelope._canonical`` and the
Verified Reel receipt (docs/VERIFIED_REEL_PLAN.md §6): ``sort_keys``, compact
separators, ASCII. ``hash`` = sha256 over the canonical body *without* the
``hash`` and ``signature`` keys. The Ed25519 signature (when present) covers
the same canonical body bytes. ``signed`` and ``key_id`` are inside the hashed
body, so stripping a signature and flipping ``signed`` breaks the hash chain.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

SCHEMA = "qoresence.truth.fact.v0"
GENESIS_HASH = "0" * 64

FACT_KINDS = ("session_start", "score_lock", "score_change", "clip_ref", "session_end")
SCORE_KINDS = ("score_lock", "score_change")

LEVEL_SCREEN_ONLY = "screen_only"
LEVEL_SCREEN_INPUT = "screen+input"
LABEL_VERIFIED = "verified"
LABEL_UNVERIFIED = "unverified"
LABEL_META = "meta"

# Keys excluded from the hashed body.
_UNHASHED = ("hash", "signature")


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def hashed_body(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if k not in _UNHASHED}


def body_bytes(record: dict[str, Any]) -> bytes:
    return canonical(hashed_body(record))


def fact_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(body_bytes(record)).hexdigest()


@dataclass
class TruthFact:
    """One line of the truth feed.

    ``scores`` is only ever set on ``score_lock`` / ``score_change`` and only
    from a licensed ConfirmTicket lock (fail-closed; see feed.py).
    """

    kind: str
    session_id: str
    clock_ns: int
    wall_utc: str
    game_profile: str | None = None
    scores: dict[str, Any] | None = None
    prev_scores: dict[str, Any] | None = None
    frame: dict[str, Any] | None = None
    source: dict[str, Any] | None = None
    controller: dict[str, Any] | None = None
    verification: dict[str, Any] | None = None
    clip: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    # Chain fields (filled by the writer)
    seq: int = -1
    prev_hash: str = GENESIS_HASH
    signed: bool = False
    key_id: str | None = None
    hash: str = ""
    signature: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.kind not in FACT_KINDS:
            raise ValueError(f"unknown truth fact kind: {self.kind!r}")

    def to_record(self) -> dict[str, Any]:
        d = asdict(self)
        d["schema"] = SCHEMA
        return d
