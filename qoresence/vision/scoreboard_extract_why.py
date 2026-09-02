"""Post-extract board_why stamp. Observation only — no bus emit, no lobe lock.

Wraps ``FootballScoreboardExtractor.extract`` so a refuse / VLM miss / mint
is classified even when the extractor module itself is unchanged.
"""

from __future__ import annotations

from typing import Any

from qoresence.vision.board_why import infer_board_why, normalize_board_why
from qoresence.vision.visual_context import VisualContext

_WRAPPED = False


def _game_state_token(ctx: VisualContext | None) -> str:
    if ctx is None:
        return ""
    try:
        return str(getattr(ctx.game_state, "value", None) or ctx.game_state or "").lower()
    except Exception:
        return ""


def _read_vlm_status() -> str:
    try:
        from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

        return str(get_scoreboard_vlm().vlm_status() or "none")
    except Exception:
        return "none"


def _stamp_board_why(ctx: VisualContext | None, why: str) -> str:
    from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor

    token = normalize_board_why(why)
    FootballScoreboardExtractor._last_board_why = token
    if ctx is None:
        return token
    ctx.board_why = token
    if not isinstance(ctx.details, dict):
        ctx.details = {}
    ctx.details["board_why"] = token
    return token


def _refuse_from_last(ctx: VisualContext, vlm: dict[str, Any] | None) -> str | None:
    if not vlm:
        return None
    home, away = vlm.get("home_score"), vlm.get("away_score")
    if home is None or away is None:
        return None
    try:
        from qoresence.vision.scoreboard_extractor import garbage_lock_reason

        return garbage_lock_reason(
            home=int(home),
            away=int(away),
            home_team=str(getattr(ctx, "home_team", "") or ""),
            away_team=str(getattr(ctx, "away_team", "") or ""),
            game_state=_game_state_token(ctx),
            crop_hash=str(getattr(ctx, "frame_hash", "") or ""),
        )
    except Exception:
        return None


def stamp_ctx(ctx: VisualContext | None) -> VisualContext | None:
    """Stamp canonical board_why on a context after extract (or refuse)."""
    if ctx is None:
        return ctx
    tid = str(getattr(ctx, "confirm_ticket_id", "") or "").strip()
    if tid and getattr(ctx, "score_vlm_locked", False):
        _stamp_board_why(ctx, infer_board_why(minted=True, confirm_ticket_id=tid))
        return ctx
    vlm = None
    try:
        from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

        vlm = get_scoreboard_vlm().get_last()
    except Exception:
        vlm = None
    why = infer_board_why(
        minted=False,
        confirm_ticket_id=tid,
        score_vlm_locked=bool(getattr(ctx, "score_vlm_locked", False)),
        refuse=_refuse_from_last(ctx, vlm),
        vlm_status=_read_vlm_status(),
        game_state=_game_state_token(ctx),
    )
    _stamp_board_why(ctx, why)
    try:
        from qoresence.graphs.refuse_chain import apply_refuse
        from qoresence.graphs.ticket_provenance import record_refuse

        sid = str(getattr(ctx, "session_id", "") or "")
        record_refuse(why, session_id=sid)
        apply_refuse(why, session_id=sid)
        if why == "vlm_none":
            from qoresence.graphs.crop_evidence import record_ticker_null

            record_ticker_null(getattr(ctx, "game_profile", None), session_id=sid)
    except Exception:
        pass
    return ctx


def ensure_wrapped() -> None:
    """Idempotent wrap of FootballScoreboardExtractor.extract."""
    global _WRAPPED
    if _WRAPPED:
        return
    from qoresence.vision.scoreboard_extractor import FootballScoreboardExtractor

    if not hasattr(FootballScoreboardExtractor, "_last_board_why"):
        FootballScoreboardExtractor._last_board_why = "unlocked"
    orig = FootballScoreboardExtractor.extract
    if getattr(orig, "_board_why_wrapped", False):
        _WRAPPED = True
        return

    def wrapped(
        self: Any,
        frame: Any,
        ctx: VisualContext | None = None,
        *,
        allow_ocr: bool | None = None,
    ) -> VisualContext:
        out = orig(self, frame, ctx, allow_ocr=allow_ocr)
        return stamp_ctx(out) or out

    wrapped._board_why_wrapped = True  # type: ignore[attr-defined]
    FootballScoreboardExtractor.extract = wrapped  # type: ignore[method-assign]
    _WRAPPED = True
