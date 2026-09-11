"""Consent-gated notary wrap. Bridge cannot grant consent.

Seal/wrap for production Recap lives on QorTroller #145 — not Deck HTTP.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .envelope import ObservationEnvelope
from .locks import DualLocks, compose_locks
from .sanitize import strip_truth_leaks


@dataclass(frozen=True)
class ConsentRecord:
    gamer: str
    granted: bool
    purpose: str
    signed_by: str
    note: str = ""

    def valid_for_wrap(self) -> bool:
        if not self.granted or not self.gamer or not self.signed_by:
            return False
        if self.signed_by.lower() != self.gamer.lower():
            return False
        if self.signed_by.lower() in {"bridge", "operator", "qortroller", "qoresence"}:
            return False
        if self.purpose not in {"portcert", "wmp", "portcert+wmp"}:
            return False
        return True


@dataclass
class WrapResult:
    status: str
    reason: str
    locks: DualLocks
    envelope_commitment: str | None
    portcert: dict | None
    wmp_precursor: dict | None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "locks": self.locks.to_hud(),
            "envelope_commitment": self.envelope_commitment,
            "portcert": self.portcert,
            "wmp_precursor": self.wmp_precursor,
        }


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _receipt_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(blob).hexdigest()}"


def wrap_notary(
    envelope: ObservationEnvelope,
    consent: ConsentRecord | None,
    *,
    coupling_present: bool | None = None,
    same_seq: bool = True,
) -> WrapResult:
    strip_truth_leaks(envelope.to_dict())
    commitment = envelope.clock_commitment
    if coupling_present is None:
        coupling_present = any(
            t.get("ticket_kind") == "coupling" and t.get("ticket_id") for t in envelope.ticks
        )
    if consent is None or not consent.valid_for_wrap():
        locks = compose_locks(
            coupling_ticket=coupling_present,
            same_seq=same_seq,
            consent_granted=False,
            wrap_sealed=False,
        )
        reason = "consent missing or invalid — bridge cannot grant"
        if consent is not None and consent.signed_by.lower() != (consent.gamer or "").lower():
            reason = "signed_by != gamer — wrap REFUSED"
        return WrapResult("REFUSED", reason, locks, commitment, None, None)
    spans: list[dict] = []
    current: dict | None = None
    for tick in envelope.ticks:
        covered = tick.get("ticket_kind") == "coupling" and bool(tick.get("ticket_id"))
        label = "coupling-covered" if covered else "gap"
        if current and current["kind"] == label:
            current["end_seq"] = tick["frame_seq"]
            current["end_ns"] = tick["clock_ns"]
            current["ticks"] += 1
        else:
            if current:
                spans.append(current)
            current = {
                "kind": label,
                "start_seq": tick["frame_seq"],
                "end_seq": tick["frame_seq"],
                "start_ns": tick["clock_ns"],
                "end_ns": tick["clock_ns"],
                "ticks": 1,
            }
    if current:
        spans.append(current)
    portcert_body: dict[str, Any] = {
        "schema": "qortroller.portcert-lite.v0",
        "plane": "truth",
        "advisory": True,
        "never_ban": True,
        "session_id": envelope.session_id,
        "clock_commitment": commitment,
        "tick_count": len(envelope.ticks),
        "sidecar_hashes": envelope.sidecar_hashes,
        "authored_spans": spans,
        "consent": {
            "gamer": consent.gamer,
            "purpose": consent.purpose,
            "granted": True,
            "signed_by": consent.signed_by,
        },
        "sealed_at": _now(),
        "ceilings": {"scope": "developer_self", "network": "off-chain-lite", "humanity_claim": False},
    }
    portcert_body["receipt"] = _receipt_hash(portcert_body)
    wmp = None
    if consent.purpose in {"wmp", "portcert+wmp"}:
        wmp = {
            "schema": "qortroller.wmp-precursor.v0",
            "channel": "action-only",
            "biometric_export": False,
            "session_id": envelope.session_id,
            "clock_commitment": commitment,
            "tickets": [
                {"ticket_id": t.get("ticket_id"), "kind": t.get("ticket_kind")}
                for t in envelope.ticks
                if t.get("ticket_id")
            ],
            "hid_edges": [t.get("hid_edge") for t in envelope.ticks if t.get("hid_edge")],
            "consent_purpose": consent.purpose,
            "note": "precursor only — not a sold bundle, no buyer implied",
        }
    locks = compose_locks(
        coupling_ticket=coupling_present,
        same_seq=same_seq,
        consent_granted=True,
        wrap_sealed=True,
    )
    return WrapResult("SEALED", "gamer-signed consent accepted", locks, commitment, portcert_body, wmp)
