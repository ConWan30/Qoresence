"""Observation-plane export only. Does not wrap, does not light TRUTH."""

from __future__ import annotations

from qoresence.compose.clock_notary.envelope import ObservationEnvelope, envelope_from_recap
from qoresence.compose.clock_notary.locks import compose_locks


def export_from_recap(recap: dict) -> dict:
    env: ObservationEnvelope = envelope_from_recap(recap)
    coupling = any(t.get("ticket_kind") == "coupling" and t.get("ticket_id") for t in env.ticks)
    locks = compose_locks(
        coupling_ticket=coupling,
        same_seq=True,
        consent_granted=False,
        wrap_sealed=False,
    )
    body = env.to_dict()
    body["locks"] = locks.to_hud()
    body["notary"] = {
        "status": "UNSEALED",
        "reason": "observation plane cannot wrap — hand envelope to QorTroller after gamer consent",
    }
    return body
