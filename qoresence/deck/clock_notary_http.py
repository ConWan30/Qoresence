"""Deck HTTP mounts for the Recap observation-export door (no seal/verify)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def mount_clock_notary(app: Any, situation_fn: Callable[[], dict] | None = None) -> None:
    from qoresence.compose.clock_notary.door import export_door

    try:
        from fastapi.responses import JSONResponse
    except Exception:  # pragma: no cover
        JSONResponse = None

    def _json(body: dict):
        if JSONResponse is None:
            return body
        return JSONResponse(body)

    @app.get("/api/session/clock-notary")
    async def api_session_clock_notary(fixture: str = "", session_id: str = ""):  # type: ignore[no-untyped-def]
        from qoresence.foundry.session_view import build_session_response

        sit = situation_fn() if situation_fn else {}
        try:
            view_env = build_session_response(
                session_id=session_id, fixture=fixture, live_situation=sit
            )
        except Exception:
            view_env = build_session_response(session_id="")
        view = view_env.get("view") if isinstance(view_env, dict) else None
        export_view = view if isinstance(view, dict) else view_env
        try:
            from qoresence.observation.runtime import observations_export_snapshot

            observations = observations_export_snapshot()
            observation_session = str(observations.get("session_id") or "")
            if observations.get("enabled") and (
                not fixture and (not session_id or observation_session == session_id)
            ):
                export_view = dict(export_view)
                export_view["observations"] = observations
        except Exception:
            # An unavailable opt-in lifecycle must not change the existing
            # observation-only export behavior; envelope_from_recap will fail
            # closed when a partial lifecycle block is supplied.
            pass
        return _json(export_door(export_view))
