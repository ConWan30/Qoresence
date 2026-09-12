"""Deck HTTP mounts for the Recap observation-export door (no seal/verify)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def mount_clock_notary(app: Any, situation_fn: Callable[[], dict] | None = None) -> None:
    from qoresence.compose.clock_notary.door import export_door
    from qoresence.compose.clock_notary.presence_pack import assemble_pack, pack_zip_bytes

    try:
        from fastapi.responses import JSONResponse, Response
    except Exception:  # pragma: no cover
        JSONResponse = None
        Response = None

    def _json(body: dict):
        if JSONResponse is None:
            return body
        return JSONResponse(body)

    def _session_export(fixture: str = "", session_id: str = "") -> dict:
        from qoresence.foundry.session_view import build_session_response

        sit = situation_fn() if situation_fn else {}
        try:
            view_env = build_session_response(
                session_id=session_id, fixture=fixture, live_situation=sit
            )
        except Exception:
            view_env = build_session_response(session_id="")
        view = view_env.get("view") if isinstance(view_env, dict) else None
        return export_door(view if isinstance(view, dict) else view_env)

    @app.get("/api/session/clock-notary")
    async def api_session_clock_notary(fixture: str = "", session_id: str = ""):  # type: ignore[no-untyped-def]
        return _json(_session_export(fixture=fixture, session_id=session_id))

    @app.get("/api/session/presence-pack")
    async def api_session_presence_pack(fixture: str = "", session_id: str = ""):  # type: ignore[no-untyped-def]
        packed = assemble_pack(_session_export(fixture=fixture, session_id=session_id))
        return _json(
            {
                "ok": packed["ok"],
                "error": packed.get("error"),
                "manifest": packed.get("manifest"),
                "listing": packed.get("listing"),
            }
        )

    @app.get("/api/session/presence-pack.zip")
    async def api_session_presence_pack_zip(fixture: str = "", session_id: str = ""):  # type: ignore[no-untyped-def]
        packed = assemble_pack(_session_export(fixture=fixture, session_id=session_id))
        if not packed.get("ok"):
            return _json({"ok": False, "error": packed.get("error") or "pack refused"})
        raw = pack_zip_bytes(packed.get("files") or {})
        if Response is None:
            return raw
        return Response(
            content=raw,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=presence-pack.zip"},
        )
