"""Independent Clock Notary checks. Do not trust wrap.status from the producer."""

from __future__ import annotations

from typing import Any

from .envelope import clock_commitment
from .io_ledger import ledger_checks
from .sanitize import strip_truth_leaks
from .wrap import ConsentRecord


def verify_wrap(wrap: dict[str, Any] | None, envelope: dict[str, Any] | None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    env = strip_truth_leaks(envelope if isinstance(envelope, dict) else {})
    w = wrap if isinstance(wrap, dict) else {}
    inner = w.get("wrap") if isinstance(w.get("wrap"), dict) else w

    ticks = list(env.get("ticks") or [])
    sidecars = dict(env.get("sidecar_hashes") or {})
    session_id = str(env.get("session_id") or "")
    recomputed = clock_commitment(session_id, ticks, sidecars) if session_id else ""
    claimed = str(env.get("clock_commitment") or "")
    add("envelope_commitment", bool(session_id) and recomputed == claimed, recomputed or "missing session")

    wrap_commit = str(inner.get("envelope_commitment") or "")
    add("wrap_points_at_envelope", bool(wrap_commit) and wrap_commit == recomputed, wrap_commit)

    portcert = inner.get("portcert") if isinstance(inner.get("portcert"), dict) else None
    add("portcert_present", portcert is not None)
    if portcert:
        add(
            "portcert_clock",
            str(portcert.get("clock_commitment") or "") == recomputed,
            str(portcert.get("clock_commitment") or ""),
        )
        add("advisory", bool(portcert.get("advisory")))
        add("never_ban", bool(portcert.get("never_ban")))
        ceilings = portcert.get("ceilings") if isinstance(portcert.get("ceilings"), dict) else {}
        add("no_humanity_claim", ceilings.get("humanity_claim") is False)
        consent = portcert.get("consent") if isinstance(portcert.get("consent"), dict) else {}
        record = ConsentRecord(
            gamer=str(consent.get("gamer") or ""),
            granted=bool(consent.get("granted")),
            purpose=str(consent.get("purpose") or "portcert"),
            signed_by=str(consent.get("signed_by") or ""),
        )
        add("gamer_signed", record.valid_for_wrap(), f"{record.signed_by} / {record.gamer}")
    else:
        add("portcert_clock", False, "no portcert")
        add("advisory", False)
        add("never_ban", False)
        add("no_humanity_claim", False)
        add("gamer_signed", False)

    leaks = [k for k in ("phi", "poep_enabled", "imu_export") if k in env or k in inner]
    add("no_truth_leaks", not leaks, ",".join(leaks))
    checks.extend(ledger_checks(env))

    passed = sum(1 for c in checks if c["ok"])
    ok = all(c["ok"] for c in checks)
    return {
        "ok": ok,
        "passed": passed,
        "total": len(checks),
        "clock_commitment": recomputed or claimed,
        "checks": checks,
        "trust": "recomputed — producer status field ignored",
    }
