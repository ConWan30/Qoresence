"""MCP helpers for Clock Notary. Observation only. Truth dest denied."""

from __future__ import annotations

import os
from typing import Any

from qoresence.compose.clock_notary.from_session import payload_from_session_view
from qoresence.vision.title_presence_wrap import dest_denied


def _grant_ok() -> tuple[bool, str]:
    grant = (os.getenv("QORESENCE_WRAP_GRANT_ID") or "").strip()
    if not grant:
        return False, "grant_missing"
    return True, grant


def handle_export_clock_envelope(session_view: dict[str, Any] | None = None) -> dict[str, Any]:
    if session_view is None:
        try:
            from qoresence.foundry.session_view import build_session_response

            session_view = build_session_response()
        except Exception as exc:
            return {
                "ok": False,
                "plane": "observation",
                "error": "session_unavailable",
                "hint": str(exc),
            }
    return payload_from_session_view(session_view)


def handle_wrap_clock_notary(dest_plane: str = "qoresence-research") -> dict[str, Any]:
    dest = str(dest_plane or "qoresence-research").strip() or "qoresence-research"
    if dest_denied(dest):
        return {
            "ok": False,
            "reason": "dest_denied",
            "dest_plane": dest,
            "wrap": None,
            "hint": "qortroller-truth is out of plane — use QorTroller scripts/clock_notary_wrap.py after gamer consent",
        }
    ok, grant = _grant_ok()
    if not ok:
        return {
            "ok": False,
            "reason": grant,
            "dest_plane": dest,
            "wrap": None,
            "hint": "set QORESENCE_WRAP_GRANT_ID",
        }
    exported = handle_export_clock_envelope()
    exported["grant_id"] = grant
    exported["dest_plane"] = dest
    exported["wrap"] = None
    exported["notary"] = {
        "status": "UNSEALED",
        "reason": "grant accepted for research dest only — truth seal is QorTroller-side",
    }
    return exported
