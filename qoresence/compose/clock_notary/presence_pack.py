"""Observation-plane Presence Pack assembler. Does not wrap. Does not list WMP."""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from qoresence.compose.clock_notary.io_ledger import canonicalize_out_edge

SCHEMA = "qoresence.presence-pack.v0"
LISTING_SCHEMA = "qoresence.presence-pack-listing.v0"
SKU = "presence-pack"
PLANE = "qoresence-observation"

FORBIDDEN_TOKENS = (
    "humanity",
    "eligible",
    "eligibility",
    "anti-cheat",
    "anticheat",
    "wmp",
    "port-cert",
    "portcert",
    "ban",
)


def _canonical_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def _hash_tail(commitment: str) -> str:
    token = str(commitment or "").strip()
    if token.startswith("sha256:"):
        token = token[7:]
    return token[-8:] if len(token) >= 8 else token


def _scan_forbidden(*blobs: Any) -> str | None:
    parts: list[str] = []
    for blob in blobs:
        if blob is None:
            continue
        if isinstance(blob, (dict, list)):
            parts.append(json.dumps(blob, ensure_ascii=True).lower())
        else:
            parts.append(str(blob).lower())
    hay = "\n".join(parts)
    for token in FORBIDDEN_TOKENS:
        if token in hay:
            return token
    return None


def _out_edge_from_ticks(ticks: Any) -> dict[str, Any] | None:
    if not isinstance(ticks, list):
        return None
    for tick in ticks:
        if not isinstance(tick, dict):
            continue
        edge = canonicalize_out_edge(tick.get("out_edge"))
        if edge:
            return edge
    return None


def assemble_pack(export_body: dict[str, Any] | None) -> dict[str, Any]:
    """Build a draft pack from an observation export. Refuse instead of inventing."""
    body = export_body if isinstance(export_body, dict) else {}
    commitment = str(body.get("clock_commitment") or "").strip()
    if not body.get("ok") or not commitment:
        return {
            "ok": False,
            "error": "export refused or clock_commitment missing",
            "manifest": None,
            "listing": None,
            "files": {},
        }

    extras = body.get("extras") if isinstance(body.get("extras"), dict) else {}
    session_id = str(body.get("session_id") or extras.get("session_id") or "")
    edge = _out_edge_from_ticks(body.get("ticks"))
    edge_state = "present" if edge else "omitted"
    tail = _hash_tail(commitment)

    listing = {
        "schema": LISTING_SCHEMA,
        "status": "draft",
        "sku": SKU,
        "plane": PLANE,
        "title": f"Session pack {session_id or 'unsigned'}",
        "blurb": "Observation envelope. Recompute the clock. Not a wrap.",
        "clock_commitment": commitment,
        "hash_tail": tail,
        "price": None,
        "out_edge": edge_state,
        "chain": "paused",
        "advisory": True,
        "never_ban": True,
    }

    hit = _scan_forbidden(extras, listing["title"], listing["blurb"], body.get("copy"))
    if hit:
        return {
            "ok": False,
            "error": f"forbidden token in pack material: {hit}",
            "manifest": None,
            "listing": None,
            "files": {},
        }

    manifest = {
        "schema": SCHEMA,
        "sku": SKU,
        "plane": PLANE,
        "session_id": session_id,
        "clock_commitment": commitment,
        "hash_tail": tail,
        "out_edge": edge_state,
        "listing_status": "draft",
        "chain": "paused",
        "notary": str((body.get("notary") or {}).get("status") or "UNSEALED"),
        "live_truth": str((body.get("door") or {}).get("live_truth") or "DARK"),
    }

    envelope = {k: v for k, v in body.items() if k != "files"}
    files: dict[str, bytes] = {
        "MANIFEST.json": _canonical_bytes(manifest),
        "observation-envelope.json": _canonical_bytes(envelope),
        "listing-draft.json": _canonical_bytes(listing),
        "sidecars.json": _canonical_bytes(body.get("sidecar_hashes") or {}),
        "VERIFY.txt": (
            "Recompute clock_commitment from observation-envelope.json.\n"
            "Ignore producer status fields. Do not treat this zip as a wrap.\n"
        ).encode("utf-8"),
    }
    if edge:
        files["out_edge.json"] = _canonical_bytes(edge)

    return {
        "ok": True,
        "error": None,
        "manifest": manifest,
        "listing": listing,
        "files": files,
    }


def pack_zip_bytes(files: dict[str, bytes] | None) -> bytes:
    members = files if isinstance(files, dict) else {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, raw in sorted(members.items()):
            zf.writestr(name, raw)
    return buf.getvalue()
