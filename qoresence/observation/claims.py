"""Claim ledger — every assertion cites supporting evidence."""

from __future__ import annotations

import hashlib
import re
from copy import deepcopy

LEDGER_SCHEMA = "observation-claim-ledger-0"

_FORBIDDEN_SUGGESTION = re.compile(
    r"\b(you panic|you choked|because you|authorship|caused the|your fault)\b",
    re.I,
)


def software_version() -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version("qoresence")
    except Exception:
        return "qoresence-dev"


def evidence_ref(event: dict) -> dict:
    tick = event.get("tick") or {}
    ref = {
        "type": "evidence",
        "evidence_id": event["evidence_id"],
        "frame_seq": tick.get("frame_seq"),
        "clock_ns": tick.get("clock_ns"),
    }
    if event.get("observation_id"):
        ref["observation_id"] = event["observation_id"]
    return ref


def clip_ref(record: dict) -> dict | None:
    clip = record.get("clip") or {}
    if clip.get("status") != "available" or not clip.get("filename"):
        return None
    return {
        "type": "clip",
        "observation_id": record["observation_id"],
        "revision": record.get("revision"),
        "filename": clip["filename"],
    }


def _claim_id(kind: str, observation_id: str, suffix: str) -> str:
    seed = f"{kind}:{observation_id}:{suffix}"
    return "clm-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


def _detector_ids(event: dict) -> tuple[str | None, str | None]:
    det = event.get("detector_output") if isinstance(event.get("detector_output"), dict) else {}
    model = event.get("model") or det.get("model")
    return model, det.get("schema_version")


def build_observation_claim(
    *,
    statement: str,
    event: dict,
    observation_id: str,
    disposition: str,
    disposition_reason: str,
) -> dict:
    detector_id, model_version = _detector_ids(event)
    refs = [evidence_ref(event)]
    return {
        "schema_version": LEDGER_SCHEMA,
        "claim_id": _claim_id("observation", observation_id, event["evidence_id"]),
        "kind": "observation",
        "observation_vs_inference": "observation",
        "statement": statement,
        "disposition": disposition,
        "disposition_reason": disposition_reason,
        "supporting_refs": refs,
        "detector_id": detector_id,
        "software_version": software_version(),
        "model_version": model_version,
    }


def build_interpretation_claim(
    *,
    statement: str,
    supporting_refs: list[dict],
    observation_id: str,
    event: dict,
    disposition: str,
    disposition_reason: str,
) -> dict:
    if not supporting_refs:
        raise ValueError("interpretation claim requires observation supporting refs")
    detector_id, model_version = _detector_ids(event)
    return {
        "schema_version": LEDGER_SCHEMA,
        "claim_id": _claim_id("interpretation", observation_id, event["evidence_id"]),
        "kind": "interpretation",
        "observation_vs_inference": "inference",
        "statement": statement,
        "disposition": disposition,
        "disposition_reason": disposition_reason,
        "supporting_refs": deepcopy(supporting_refs),
        "detector_id": detector_id,
        "software_version": software_version(),
        "model_version": model_version,
    }


def build_suggestion_claim(
    *,
    statement: str,
    supporting_refs: list[dict],
    observation_id: str,
    sample_size: int,
    uncertainty: str,
    disposition: str,
    disposition_reason: str,
) -> dict:
    if _FORBIDDEN_SUGGESTION.search(statement):
        raise ValueError("suggestion cannot invent causation or authorship")
    if sample_size < 0:
        raise ValueError("sample_size must be non-negative")
    return {
        "schema_version": LEDGER_SCHEMA,
        "claim_id": _claim_id("suggestion", observation_id, str(sample_size)),
        "kind": "suggestion",
        "observation_vs_inference": "inference",
        "statement": statement,
        "disposition": disposition,
        "disposition_reason": disposition_reason,
        "supporting_refs": deepcopy(supporting_refs),
        "sample_size": sample_size,
        "uncertainty": uncertainty,
        "detector_id": None,
        "software_version": software_version(),
        "model_version": None,
    }


def validate_claim(claim: dict) -> None:
    if claim.get("schema_version") != LEDGER_SCHEMA:
        raise ValueError("unsupported claim schema")
    kind = claim.get("kind")
    refs = claim.get("supporting_refs") or []
    if kind == "interpretation" and not refs:
        raise ValueError("interpretation claim missing observation refs")
    if kind == "suggestion":
        if _FORBIDDEN_SUGGESTION.search(str(claim.get("statement", ""))):
            raise ValueError("suggestion invents causation or authorship")
        if "sample_size" not in claim:
            raise ValueError("suggestion missing sample_size")
    if kind == "observation" and not refs:
        raise ValueError("observation claim missing supporting refs")


def _upsert(ledger: list[dict], claim: dict) -> None:
    validate_claim(claim)
    for index, existing in enumerate(ledger):
        if existing.get("claim_id") == claim["claim_id"]:
            ledger[index] = claim
            return
    ledger.append(claim)


def sync_ledger(record: dict, event: dict, *, phase: str | None, game_state: str | None) -> None:
    """Attach ledger claims to the observation revision (deterministic, replay-safe)."""
    ledger = list(record.get("ledger") or [])
    observation_id = record["observation_id"]
    base_ref = evidence_ref(event)

    if event["kind"] == "visual" and record.get("state") in {"candidate", "tracking"}:
        phase_label = phase or "unknown"
        interpretation = build_interpretation_claim(
            statement=f"Resembles active football phase ({phase_label})",
            supporting_refs=[base_ref],
            observation_id=observation_id,
            event=event,
            disposition="accepted",
            disposition_reason="visual_phase_in_active_allowlist",
        )
        interpretation["claim_id"] = _claim_id("interpretation", observation_id, "phase")
        _upsert(ledger, interpretation)

    if record.get("state") == "confirmed" and record.get("claims"):
        score = record["claims"][0]
        observation = build_observation_claim(
            statement=(
                f"Licensed scoreboard observation: {score.get('home')}–{score.get('away')}"
            ),
            event=event,
            observation_id=observation_id,
            disposition="accepted",
            disposition_reason="confirm_ticket_licensed_at_emission",
        )
        observation["claim_id"] = _claim_id("observation", observation_id, "scoreboard")
        clip = clip_ref(record)
        if clip:
            observation["supporting_refs"].append(clip)
        _upsert(ledger, observation)

    if record.get("state") == "partial":
        suggestion = build_suggestion_claim(
            statement="Review comparable plays when more labeled samples are available",
            supporting_refs=[base_ref],
            observation_id=observation_id,
            sample_size=0,
            uncertainty="qualification_withheld",
            disposition="withheld",
            disposition_reason="scoreboard_not_licensed",
        )
        suggestion["claim_id"] = _claim_id("suggestion", observation_id, "review")
        _upsert(ledger, suggestion)

    record["ledger"] = ledger
