"""Versioned observation records. Reducer has no clock, IO or model calls."""

from __future__ import annotations

import json
import os
from copy import deepcopy

from qoresence.compose.clock_notary.envelope import Tick
from qoresence.observation.adapters.football import FOOTBALL_ADAPTER
from qoresence.observation.adapters.football import POLICY_VERSION as POLICY

JOURNAL_SCHEMA = "observation-journal-1"
DETECTOR_SCHEMA = "observation-detector-1"


def event_replay_enabled() -> bool:
    return os.getenv("QORESENCE_EVENT_REPLAY", "").strip().lower() in {"1", "true", "on"}


def observations_enabled() -> bool:
    return os.getenv("QORESENCE_OBSERVATIONS", "").strip().lower() in {"1", "true", "on"}


def _evidence_phase(evidence: dict) -> str | None:
    det = evidence.get("detector_output")
    if isinstance(det, dict) and det.get("visual_phase") is not None:
        return str(det.get("visual_phase"))
    phase = evidence.get("phase")
    return str(phase) if phase is not None else None


def _evidence_game_state(evidence: dict) -> str | None:
    det = evidence.get("detector_output")
    if isinstance(det, dict) and det.get("game_state") is not None:
        return str(det.get("game_state"))
    state = evidence.get("game_state")
    return str(state) if state is not None else None


def freeze_detector_output(payload: dict) -> dict:
    """Freeze detector/VLM fields at emission. Replay never calls external models."""
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    football = payload.get("football") if isinstance(payload.get("football"), dict) else {}
    return {
        "schema_version": DETECTOR_SCHEMA,
        "visual_phase": payload.get("visual_phase") or details.get("visual_phase"),
        "game_state": payload.get("game_state"),
        "game_category": payload.get("game_category"),
        "model": payload.get("model"),
        "frame_hash": payload.get("frame_hash"),
        "confidence": payload.get("visual_confidence", payload.get("confidence")),
        "home_score": football.get("home_score"),
        "away_score": football.get("away_score"),
    }


def pack_journal_row(
    evidence: dict,
    record: dict,
    *,
    policy_version: str = POLICY,
) -> dict:
    return {
        "schema_version": JOURNAL_SCHEMA,
        "policy_version": policy_version,
        "evidence": deepcopy(evidence),
        "record": deepcopy(record),
    }


def parse_journal_row(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("observation journal row is not an object")
    schema = raw.get("schema_version")
    if schema is not None and schema != JOURNAL_SCHEMA:
        raise ValueError("unsupported observation journal schema")
    for key in ("policy_version", "evidence", "record"):
        if key not in raw:
            raise ValueError(f"observation journal row missing {key}")
    return raw


def load_journal_lines(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        rows.append(parse_journal_row(json.loads(line)))
    return rows


def _policy_adapter(policy_version: str):
    if policy_version == FOOTBALL_ADAPTER.policy_version:
        return FOOTBALL_ADAPTER
    raise ValueError("unsupported observation policy")


def reduce_observation(previous: dict | None, event: dict, policy_version: str = POLICY) -> dict | None:
    """Reduce normalized evidence in arrival order; late events never reopen intervals.

    Confirmation qualifies a scoreboard observation, NOT a causal play outcome.
    The caller journals normalized evidence, including frozen ticket qualification.
    """
    adapter = _policy_adapter(policy_version)
    if previous and previous["policy_version"] != policy_version:
        raise ValueError("cannot silently change observation policy")
    record = deepcopy(previous)
    clock = event["tick"]["clock_ns"]
    eid = event["evidence_id"]
    if not eid or event["tick"].get("evidence_id") != eid:
        raise ValueError("envelope tick requires the bus evidence id")
    phase = _evidence_phase(event)
    game_state = _evidence_game_state(event)
    if record and (
        eid in record["evidence_ids"]
        or (event["kind"] != "clip" and clock < record["last_clock_ns"])
    ):
        return record
    if event["kind"] == "visual" and adapter.should_open_moment(phase, record):
        record = adapter.new_candidate_record(event, clock, eid, policy_version)
    if record is None or event["session_id"] != record["session_id"]:
        return record
    if event["kind"] == "clip":
        if event.get("observation_id") != record["observation_id"]:
            return record
        record["clip"] = event["clip"]
    elif event["kind"] == "gap":
        record["uncertainty"] = sorted(set(record["uncertainty"] + ["evidence_dropped"]))
        record["state"] = "unresolved"
        record["end_ns"] = record["end_ns"] or clock
    elif event["kind"] == "visual":
        if record["end_ns"] is None:
            if adapter.should_close_moment(phase, game_state):
                record["end_ns"] = clock
                record["state"] = "provisional"
            elif clock - record["start_ns"] > adapter.moment_boundary_timeout_ns():
                record["end_ns"] = clock
                record["state"] = "unresolved"
                record["uncertainty"].append("boundary_timeout")
            elif record["revision"]:
                record["state"] = "tracking"
        # Late qualification is deliberately bounded to eight seconds after closure.
        if record["end_ns"] is not None and clock - record["end_ns"] <= 8_000_000_000:
            claim = adapter.qualified_claim(event)
            if claim and "evidence_dropped" not in record["uncertainty"]:
                record["claims"] = [dict(claim, evidence_id=eid)]
                record["state"] = "confirmed"
            elif record["state"] == "provisional":
                record["state"] = "partial"
    else:
        return record
    from qoresence.observation.claims import sync_ledger
    from qoresence.observation.uncertainty import refresh_uncertainty_channels

    refresh_uncertainty_channels(record, event)
    sync_ledger(record, event, phase=phase, game_state=game_state)
    record["revision"] += 1
    record["last_clock_ns"] = max(clock, record["last_clock_ns"])
    record["evidence_ids"] = record["evidence_ids"] + [eid]
    return record


def normalize_visual(event: dict) -> dict | None:
    """Delegate to the game adapter; abstain for non-football categories."""
    from qoresence.observation.adapters import resolve_adapter

    p = event.get("payload", {})
    adapter = resolve_adapter(p.get("game_category"))
    if adapter is None:
        return None
    return adapter.normalize_visual(event)


def qualified_claim(evidence: dict) -> dict | None:
    """Pure check of the frozen qualification; no live ticket-book reads."""
    from qoresence.sync.seqgate import license_digits

    claim, tick = evidence.get("score_claim"), evidence["tick"]
    if not isinstance(claim, dict) or claim.get("kind") != "historical_scoreboard":
        return None
    ticket = claim.get("ticket") or {}
    if (ticket.get("session_id") != evidence["session_id"]
            or ticket.get("ticket_id") != tick.get("ticket_id")
            or tick.get("ticket_kind") != "confirm"
            or (claim.get("home"), claim.get("away")) != (ticket.get("home_score"), ticket.get("away_score"))
            or claim.get("home") is None or claim.get("away") is None
            or tick.get("score_digits") != f'{claim["home"]}-{claim["away"]}'):
        return None
    age = tick["clock_ns"] - int(ticket.get("clock_ns") or 0)
    if not 0 <= age <= 8_000_000_000 or claim.get("qualification", {}).get("licensed") is not True:
        return None
    gate = license_digits(confirm_ticket_id=ticket.get("ticket_id", ""),
                          score_vlm_locked=True, path="confirm",
                          ticket_crop_hash=ticket.get("crop_hash", ""),
                          live_crop_hash=ticket.get("crop_hash", ""),
                          ticket_clock_ns=ticket["clock_ns"], live_clock_ns=tick["clock_ns"])
    return deepcopy(claim) if gate["licensed"] else None


def emission_tick(
    *, frame_seq: int | None, clock: int, evidence_id: str, claim: dict | None
) -> dict:
    """Use the existing envelope Tick, never infer either HID leg from pixels."""
    ticket = claim["ticket"] if claim else {}
    return Tick(clock_ns=clock, frame_seq=int(frame_seq or ticket.get("frame_seq") or 0),
                ticket_id=ticket.get("ticket_id"), ticket_kind="confirm" if claim else None,
                hid_edge=None, score_digits=f'{claim["home"]}-{claim["away"]}' if claim else None,
                score_vlm_locked=claim is not None, evidence_id=evidence_id).as_commit_triple()


def journal_bytes(rows: list[dict]) -> bytes:
    return b"".join((json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
                     + "\n").encode("utf-8") for row in rows)


def replay_journal(rows: list[dict], *, session_id: str) -> list[dict]:
    """Verify every revision from envelope-sidecar evidence, including old clip results."""
    records, current = {}, None
    for row in rows:
        row = parse_journal_row(row)
        evidence = row["evidence"]
        if evidence["session_id"] != session_id:
            raise ValueError("observation journal session mismatch")
        if evidence.get("score_claim") and qualified_claim(evidence) is None:
            raise ValueError("unqualified scoreboard evidence")
        previous = records.get(evidence.get("observation_id")) if evidence["kind"] == "clip" else current
        record = reduce_observation(previous, evidence, row["policy_version"])
        if record is None or record != row["record"]:
            raise ValueError("observation journal replay mismatch")
        records[record["observation_id"]] = record
        if evidence["kind"] != "clip" or (current and record["observation_id"] == current["observation_id"]):
            current = record
    return list(records.values())


def freeze_score_claim(context: dict, clock: int) -> dict | None:
    """Freeze the existing seeing-path ticket at emission, before asynchronous reduction."""
    from qoresence.sync.seqgate import license_digits
    from qoresence.vision.confirm_ticket import get_ticket_book, ticket_is_licensed_lock

    ticket = get_ticket_book().get(context.get("confirm_ticket_id"))
    if not ticket_is_licensed_lock(ticket) or ticket is None:
        return None
    score = context.get("football") or {}
    if (score.get("home_score"), score.get("away_score")) != (ticket.home_score, ticket.away_score):
        return None
    if not 0 <= clock - ticket.clock_ns <= 8_000_000_000:
        return None
    gate = license_digits(
        confirm_ticket_id=ticket.ticket_id,
        score_vlm_locked=context.get("score_vlm_locked") is True,
        path="confirm",
        ticket_crop_hash=ticket.crop_hash,
        live_crop_hash=ticket.crop_hash,
        ticket_clock_ns=ticket.clock_ns,
        live_clock_ns=clock,
        home_score=ticket.home_score,
        away_score=ticket.away_score,
    )
    if not gate["licensed"]:
        return None
    return {
        "kind": "historical_scoreboard",
        "home": ticket.home_score,
        "away": ticket.away_score,
        "ticket": ticket.to_dict(),
        "qualification": gate,
        "meaning": "scoreboard observed; play outcome unassigned",
    }
