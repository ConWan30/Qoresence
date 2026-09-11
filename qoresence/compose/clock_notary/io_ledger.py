"""DualSense I/O ledger on the shared clock.

Three optional legs per tick:
  in   — optical / coupling (Qoresence eyes)
  edge — hid_edge when a real pad report exists
  out  — console receipt (rumble / trigger / LED opcode hash)

Honest absence is success. DualSense-on-PS5 often has no PC HID and no
output reports; do not invent either. Never hash a waveform. Never derive
out_edge from HDMI or from hid_edge alone.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

ALLOWED_KINDS = frozenset({"rumble", "trigger", "led", "unknown"})
_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")
_WAVE = frozenset({"samples", "waveform", "raw", "imu", "rumble_imu", "audio"})


def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def opcode_hash(opcode: str, *, kind: str = "unknown") -> str:
    material = {"kind": kind if kind in ALLOWED_KINDS else "unknown", "opcode": str(opcode)}
    return "sha256:" + hashlib.sha256(_canonical(material)).hexdigest()


def canonicalize_out_edge(raw: Any) -> dict[str, Any] | None:
    """Commit-safe out_edge or None (omit — honest absence)."""
    if raw is None:
        return None
    if isinstance(raw, str):
        token = raw.strip()
        if _HASH.match(token):
            return {"present": True, "kind": "unknown", "opcode_hash": token, "lag_ns": None}
        if not token:
            return None
        return {
            "present": True,
            "kind": "unknown",
            "opcode_hash": opcode_hash(token, kind="unknown"),
            "lag_ns": None,
        }
    if not isinstance(raw, dict):
        return None
    if any(k in raw for k in _WAVE):
        return None
    kind = str(raw.get("kind") or "unknown").strip().lower()
    if kind not in ALLOWED_KINDS:
        kind = "unknown"
    digest = raw.get("opcode_hash")
    if isinstance(digest, str) and _HASH.match(digest.strip()):
        hashed = digest.strip()
    elif raw.get("opcode") not in (None, ""):
        hashed = opcode_hash(str(raw.get("opcode")), kind=kind)
    else:
        present = raw.get("present")
        if present in (False, None, "", 0):
            return None
        return None
    lag = raw.get("lag_ns")
    try:
        lag_ns = int(lag) if lag is not None else None
    except (TypeError, ValueError):
        lag_ns = None
    return {"present": True, "kind": kind, "opcode_hash": hashed, "lag_ns": lag_ns}


def out_edge_from_event(ev: dict[str, Any] | None) -> dict[str, Any] | None:
    """Only from explicit output fields. Never from picture or hid_edge."""
    if not isinstance(ev, dict):
        return None
    for key in ("out_edge", "pad_out", "output"):
        block = ev.get(key)
        if block in (None, "", {}, []):
            continue
        if isinstance(block, dict) and any(
            k in block for k in ("crop", "frame", "pixels", "hdmi", "score")
        ):
            continue
        edge = canonicalize_out_edge(block)
        if edge is not None:
            return edge
    return None


def tick_out_honest(tick: dict[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(tick, dict):
        return True, "no tick"
    raw = tick.get("out_edge")
    if raw is None:
        return True, "absent"
    if isinstance(raw, dict) and any(k in raw for k in _WAVE):
        return False, "waveform"
    edge = canonicalize_out_edge(raw)
    if edge is None:
        return False, "present_without_hash"
    if not _HASH.match(str(edge.get("opcode_hash") or "")):
        return False, "bad_hash"
    return True, edge["kind"]


def ledger_checks(envelope: dict[str, Any] | None) -> list[dict[str, Any]]:
    env = envelope if isinstance(envelope, dict) else {}
    ticks = list(env.get("ticks") or [])
    hid_on_console = bool(env.get("hid_on_console", True))
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    bad = []
    present = 0
    for i, tick in enumerate(ticks):
        if not isinstance(tick, dict):
            continue
        ok, detail = tick_out_honest(tick)
        if not ok:
            bad.append(f"{i}:{detail}")
        if tick.get("out_edge"):
            present += 1
    add("out_edge_honest", not bad, ",".join(bad) or "ok")
    add(
        "out_edge_optional",
        True,
        f"present={present} absent={len(ticks) - present} hid_on_console={hid_on_console}",
    )
    if hid_on_console and present == 0:
        add("ps5_empty_io_success", True, "no pad reports on this host")
    else:
        add("ps5_empty_io_success", True, "n/a")
    return checks
