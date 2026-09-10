"""Gamer-facing notary door. Theater may export; only the gamer may seal."""

from __future__ import annotations

from typing import Any

from .envelope import ObservationEnvelope, envelope_from_recap
from .from_session import payload_from_session_view
from .verify import verify_wrap
from .wrap import ConsentRecord, wrap_notary

SEAL_PHRASE = "I am the gamer"
RESERVED_SIGNERS = frozenset({"bridge", "operator", "qortroller", "qoresence"})


def _as_view(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    if isinstance(raw.get("view"), dict):
        return raw["view"]
    return raw


def export_door(session_view: dict[str, Any] | None) -> dict[str, Any]:
    """Observation export for Recap. TRUTH stays dark."""
    view = _as_view(session_view)
    body = payload_from_session_view(view)
    body["door"] = {
        "step": "export",
        "live_truth": "DARK",
        "copy": "Eyes only. Seal is a later door — type the gamer phrase to stamp this clock.",
        "next": ["download envelope", "sign as the gamer", "copy hash for Discord"],
        "seal_phrase": SEAL_PHRASE,
        "chain": "paused",
    }
    return body


def envelope_from_payload(payload: dict[str, Any]) -> ObservationEnvelope | None:
    raw = payload.get("envelope") if isinstance(payload.get("envelope"), dict) else payload
    if not isinstance(raw, dict):
        return None
    if raw.get("schema") == "qoresence.observation-envelope.v0" and raw.get("clock_commitment"):
        return ObservationEnvelope(
            schema=raw["schema"],
            session_id=str(raw.get("session_id") or ""),
            plane=str(raw.get("plane") or "observation"),
            title_plane=str(raw.get("title_plane") or "observation"),
            hid_on_console=bool(raw.get("hid_on_console", True)),
            ticks=list(raw.get("ticks") or []),
            sidecar_hashes=dict(raw.get("sidecar_hashes") or {}),
            clock_commitment=str(raw.get("clock_commitment")),
            extras=dict(raw.get("extras") or {}),
        )
    try:
        return envelope_from_recap(raw)
    except Exception:
        return None


def _consent_from_payload(payload: dict[str, Any]) -> ConsentRecord | None:
    gamer = str(payload.get("gamer") or "").strip()
    signed_by = str(payload.get("signed_by") or gamer).strip()
    purpose = str(payload.get("purpose") or "portcert").strip().lower()
    phrase = str(payload.get("phrase") or "").strip()
    granted = bool(payload.get("granted"))
    if phrase != SEAL_PHRASE:
        return None
    if signed_by.lower() in RESERVED_SIGNERS or gamer.lower() in RESERVED_SIGNERS:
        return None
    wallet = str(payload.get("wallet") or "").strip()
    note = "local-door v0; chain paused"
    if wallet:
        note += f"; wallet={wallet}"
    return ConsentRecord(
        gamer=gamer,
        granted=granted,
        purpose=purpose if purpose in {"portcert", "wmp", "portcert+wmp"} else "portcert",
        signed_by=signed_by,
        note=note,
    )


def discord_card(*, status: str, commitment: str | None, session_id: str, receipt: str | None) -> str:
    short = (commitment or "sha256:—")[-12:]
    lines = [
        f"Clock Notary {status}",
        f"session {session_id or '—'}",
        f"clock {commitment or '—'}",
        f"tail {short}",
    ]
    if receipt:
        lines.append(f"receipt {receipt}")
    lines.append("advisory · never-ban · not a humanity claim")
    return "\n".join(lines)


def seal_door(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}
    env = envelope_from_payload(raw)
    if env is None or not env.session_id:
        return {
            "ok": False,
            "status": "REFUSED",
            "reason": "no_envelope",
            "hint": "export the Recap first",
            "wrap": None,
        }
    consent = _consent_from_payload(raw)
    if consent is None:
        return {
            "ok": False,
            "status": "REFUSED",
            "reason": "phrase_or_signer",
            "hint": f'type exactly "{SEAL_PHRASE}" and set signed_by to the gamer handle — not bridge/operator',
            "clock_commitment": env.clock_commitment,
            "wrap": None,
        }
    result = wrap_notary(env, consent)
    card = discord_card(
        status=result.status,
        commitment=result.envelope_commitment,
        session_id=env.session_id,
        receipt=(result.portcert or {}).get("receipt") if result.portcert else None,
    )
    return {
        "ok": result.status == "SEALED",
        "status": result.status,
        "reason": result.reason,
        "clock_commitment": result.envelope_commitment,
        "locks": result.locks.to_hud(),
        "wrap": result.to_dict(),
        "discord_card": card,
        "chain": "paused",
        "plane_note": "LIVE Theater stays OBS-only. This seal lives on the Recap door.",
    }


def verify_door(wrap: dict[str, Any] | None, envelope: dict[str, Any] | None) -> dict[str, Any]:
    return verify_wrap(wrap, envelope)
