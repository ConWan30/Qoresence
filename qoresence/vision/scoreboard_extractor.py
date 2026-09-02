"""Local scoreboard OCR + parsing for NCAA football frames.

Uses EasyOCR on a bottom-center crop and extracts score, quarter, clock,
down/distance, and play-clock from the HUD. No cloud VLM calls.

Score updates are **stabilized** (temporal consensus + plausible deltas) so a
single misread like 17-2 cannot wipe a real 17-17.
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from qoresence.vision.visual_context import GameCategory, VisualContext

log = logging.getLogger(__name__)

# Football scoring increments (one team) — used for plausibility, not hard law
_PLAUSIBLE_SCORE_DELTAS = frozenset({0, 1, 2, 3, 6, 7, 8})


def _normalize_quarter_word(token: str) -> str:
    """Fix common OCR mis-reads for quarter/down tokens (Jst -> 1st, etc.)."""
    token = token.strip()
    if re.match(r"^[JjIiLlZz]st$", token, re.IGNORECASE):
        return "1st"
    if re.match(r"^[2Zz]nd$", token, re.IGNORECASE):
        return "2nd"
    if re.match(r"^[3Zz]rd$", token, re.IGNORECASE):
        return "3rd"
    if re.match(r"^[4A-Za-z]th$", token, re.IGNORECASE):
        # 4th is usually clear, but sometimes OCR drops the 4
        if token[0].lower() in "th":
            return "4th"
    return token


def _fix_digits_in(token: str) -> str:
    """Replace letters that look like digits, for short numeric tokens."""
    if re.search(r"[a-z]{2,}", token, re.IGNORECASE):
        # Contains a word, don't mangle it
        return token
    mapping = str.maketrans(
        {
            "J": "1",
            "j": "1",
            "I": "1",
            "i": "1",
            "l": "1",
            "L": "1",
            "O": "0",
            "o": "0",
            "S": "5",
            "s": "5",
            "B": "8",
            "b": "8",
            "G": "6",
            "g": "6",
            "Z": "2",
            "z": "2",
            "T": "7",
            "t": "7",
            "|": "",
            ":": "",
        }
    )
    return token.translate(mapping)


_LOADING_STATES = frozenset({"loading", "cutscene", "intro", "replay"})
_MENU_STATES = frozenset({"menu", "paused", "lobby", "results", "spectating"})


def _game_state_token(ctx: VisualContext | None) -> str:
    if ctx is None:
        return ""
    try:
        return str(getattr(ctx.game_state, "value", None) or ctx.game_state or "").lower()
    except Exception:
        return ""


def _may_mint_lock(ctx: VisualContext | None, vlm: dict[str, Any] | None = None) -> bool:
    """New locks during gameplay, or on football HUD when classifier says menu.

    Play-call / pause still paints the match scorebug. Refusing mint there
    left confirm empty while DeepSeek already had NO 0 / DAL 10.

    OPERATOR LAW: Refuse lock on loading/cutscene (garbage boards during matchup swap).
    """
    if ctx is None:
        return False
    gst = _game_state_token(ctx)
    if gst in _LOADING_STATES:
        return False
    if gst in {"", "gameplay", "playing", "in_game"}:
        return True
    if not _vlm_board_grounded(vlm):
        return False
    profile = str(getattr(ctx, "game_profile", "") or "").lower()
    title = str(getattr(ctx, "game_title", "") or "").lower()
    return any(k in profile or k in title for k in ("madden", "cfb", "football", "ncaa"))


def garbage_lock_reason(
    *,
    home: int,
    away: int,
    home_team: str = "",
    away_team: str = "",
    game_state: str = "",
    book: Any = None,
) -> str | None:
    """Why this pair must not mint. None = lock may proceed.

    Receipt 1.1: refuse 0-0 after identity swap (not every 0-0), refuse 82-86-class
    first locks, refuse a live-identity ticker swap (9-47 DAL-DET over IND-DET).
    """
    gst = str(game_state or "").lower()
    if gst in _LOADING_STATES:
        return "game_state"
    if _ScoreStabilizer._looks_suspicious_pair((home, away)):
        return "suspicious_pair"

    if book is None:
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            book = get_ticket_book()
        except Exception:
            book = None
    ident = book.last_board_identity() if book is not None else None
    stale = bool(book.identity_stale()) if book is not None else False
    ht = str(home_team or "").strip()
    at = str(away_team or "").strip()

    if ident is not None:
        prior_h, prior_a, prior_ht, prior_at = ident
        teams_changed = False
        if prior_ht and prior_at and ht and at:
            try:
                from qoresence.vision.confirm_ticket import board_sides_same

                teams_changed = not board_sides_same(prior_ht, prior_at, ht, at)
            except Exception:
                prior_pair = {prior_ht.strip().upper(), prior_at.strip().upper()}
                now_pair = {ht.strip().upper(), at.strip().upper()}
                teams_changed = prior_pair != now_pair
        if home == 0 and away == 0:
            if teams_changed:
                return "zero_zero_after_identity_swap"
            if (prior_h or 0) > 0 or (prior_a or 0) > 0:
                return "zero_zero_after_nonzero"
        if teams_changed and not stale:
            return "identity_swap"

    if home == 0 and away == 0 and gst in _MENU_STATES:
        return "zero_zero_menu"
    return None


def _vlm_board_grounded(vlm: dict[str, Any] | None) -> bool:
    """True when DeepSeek reported this match's scorebug, not a lone invented pair.

    HUD blob reads fail on 640×480 Madden, so a grounded gameplay referee must
    be allowed to mint without local digits. Bare ``home/away`` (+ optional
    quarter) is how 3-2 locked on an empty HUD — refuse that.
    """
    if not vlm:
        return False
    if vlm.get("home_score") is None or vlm.get("away_score") is None:
        return False
    left = str(vlm.get("left_team") or "").strip()
    right = str(vlm.get("right_team") or "").strip()
    if left and right:
        return True
    clock = vlm.get("clock_seconds")
    if clock is None:
        return False
    try:
        int(clock)
    except (TypeError, ValueError):
        return False
    return vlm.get("quarter") is not None or vlm.get("down") is not None


def _normalize_clock(token: str) -> int | None:
    """Return clock_seconds from tokens like '1:41', '141', '1341'."""
    t = _fix_digits_in(token).strip()
    if not t:
        return None
    m = re.match(r"^(\d{1,2}):(\d{2})$", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    if re.match(r"^\d{3,4}$", t):
        if len(t) == 3:
            return int(t[0]) * 60 + int(t[1:])
        return int(t[:2]) * 60 + int(t[2:])
    return None


@dataclass
class _Token:
    text: str
    x: float  # normalized center x (0..1)
    y: float  # normalized center y (0..1)
    conf: float
    area: float = 0.0  # box area fraction (score digits >> badges)


@dataclass
class _Cluster:
    text: str
    x: float
    y: float
    conf: float


class _ScoreStabilizer:
    """Require consensus before publishing score changes (anti-OCR flicker)."""

    def __init__(self, window: int = 5, need: int = 2) -> None:
        self._window = max(3, int(window))
        self._need = max(2, int(need))
        self._recent: deque[tuple[int | None, int | None]] = deque(maxlen=self._window)
        self._stable: tuple[int | None, int | None] = (None, None)

    def update(self, home: int | None, away: int | None) -> tuple[int | None, int | None]:
        """Return stabilized (home, away). May keep previous if new read is flaky."""
        if home is None and away is None:
            return self._stable

        # Clamp football-ish range
        if home is not None and not (0 <= home <= 99):
            home = None
        if away is not None and not (0 <= away <= 99):
            away = None
        if home is None and away is None:
            return self._stable

        cand = (home, away)
        self._recent.append(cand)

        sh, sa = self._stable

        # First lock-in: BOTH sides required; never lock asymmetric garbage (12-2, 17-2)
        if sh is None and sa is None:
            if home is None or away is None:
                return self._stable
            if self._looks_suspicious_pair(cand):
                # Do not lock — wait for a coherent pair (e.g. 17-17)
                log.debug("scoreboard skip suspicious lock-in %s-%s", home, away)
                return self._stable
            need = self._need
            if self._count_pair(cand) >= need:
                self._stable = cand
                log.info("scoreboard lock-in %s-%s", cand[0], cand[1])
            return self._stable

        # Same as stable — refresh
        if cand == self._stable:
            return self._stable

        # Partial update: fill only missing side from stable
        merged_h = home if home is not None else sh
        merged_a = away if away is not None else sa
        merged = (merged_h, merged_a)

        if merged == self._stable:
            return self._stable

        # Reject implausible jumps (score drops / 17→2) unless very strong consensus
        need = self._need
        if not self._plausible_transition(self._stable, merged):
            need = self._need + 3  # e.g. 5 agreeing frames to overturn a stable score
            if self._count_pair(merged) < need:
                log.debug(
                    "scoreboard reject flaky %s-%s (stable %s-%s, need %s)",
                    merged[0],
                    merged[1],
                    sh,
                    sa,
                    need,
                )
                return self._stable

        # Accept change only after repeated agreement
        if self._count_pair(merged) >= need:
            log.info(
                "scoreboard update %s-%s → %s-%s (consensus x%s)",
                sh,
                sa,
                merged[0],
                merged[1],
                need,
            )
            self._stable = merged
            return self._stable

        # Hold stable; wait for more frames
        return self._stable

    def _count_pair(self, pair: tuple[int | None, int | None]) -> int:
        return sum(1 for p in self._recent if p == pair)

    @staticmethod
    def _looks_suspicious_pair(pair: tuple[int | None, int | None]) -> bool:
        h, a = pair
        if h is None or a is None:
            return True
        # Receipt 1.1: 82-86 after a matchup swap is ticker/clock garbage, not football.
        # 0-0 is a real kickoff — refuse that only after an identity swap, not here.
        if max(h, a) > 70 or min(h, a) >= 50:
            return True
        # One side multi-digit / large, other tiny 1–4 → down/quarter/play-clock leak
        # Classic failures: 17-2, 12-2, 21-1
        # 1–2 (and 4) next to a large score look like down/quarter leaks.
        # 0 is a shutout; 3 is a field goal — those are real football.
        if (h >= 10 and a in (1, 2, 4)) or (a >= 10 and h in (1, 2, 4)):
            return True
        if (h >= 7 and a in (1, 2, 4)) or (a >= 7 and h in (1, 2, 4)):
            return True
        # Huge imbalance with tiny side (e.g. 28-1 mid-game OCR glitch)
        # Allow true 20-0 / 28-0 blowouts (zero is valid football)
        if min(h, a) == 0 and max(h, a) <= 80:
            return False
        if min(h, a) in (1, 2) and max(h, a) >= 14:
            return True
        return False

    @staticmethod
    def _plausible_transition(
        old: tuple[int | None, int | None],
        new: tuple[int | None, int | None],
    ) -> bool:
        oh, oa = old
        nh, na = new
        if oh is None or oa is None or nh is None or na is None:
            return True
        dh = nh - oh
        da = na - oa
        # Both sides change at once is rare (except rare simultaneous / OCR flip)
        if dh != 0 and da != 0:
            # Allow both to correct toward a tie / similar values if close
            if abs(nh - na) <= 3 and abs(oh - oa) > 8:
                return True  # correcting a bad prior
            # Simultaneous changes need consensus (caller checks count)
            return False
        # Score should not drop unless correcting OCR (large drop is suspicious)
        if dh < 0 or da < 0:
            # Single-digit drop from 17→2 is classic OCR failure
            drop = abs(min(dh, 0)) + abs(min(da, 0))
            if drop >= 7:
                return False
            return False  # any drop requires consensus
        # Increase: typical football increments
        for d in (dh, da):
            if d == 0:
                continue
            if d not in _PLAUSIBLE_SCORE_DELTAS and d not in (4, 5, 9, 10, 14):
                # Unusual but allow safety with consensus later
                return d <= 14
        return True


class FootballScoreboardExtractor:
    """Extract football scoreboard fields from a BGR frame.

    Uses pluggable engines (PaddleOCR preferred for gaming HUDs, EasyOCR fallback).
    Env: ``QORESENCE_SCOREBOARD_OCR=auto|paddle|easyocr|tesseract``.
    """

    # Process-wide stabilizer so multi-instance extractors share consensus
    _stabilizer: _ScoreStabilizer | None = None
    _engine_name: str | None = None

    def __init__(self) -> None:
        if FootballScoreboardExtractor._stabilizer is None:
            FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)
        # Heavy Paddle/EasyOCR warmup is opt-in. Auto-start fights DShow and
        # freezes LIVE (age_s climbs → watchdog rebind → native crash).
        import os

        ocr_on = os.environ.get("QORESENCE_EASY_OCR", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if not ocr_on:
            return
        try:
            from qoresence.vision.scoreboard_ocr_engine import get_scoreboard_engine

            eng = get_scoreboard_engine()
            eng.start_warmup()
            FootballScoreboardExtractor._engine_name = getattr(eng, "name", None)
        except Exception as e:
            log.debug("scoreboard engine init: %s", e)

    def extract(
        self,
        frame: np.ndarray,
        ctx: VisualContext | None = None,
        *,
        allow_ocr: bool | None = None,
    ) -> VisualContext:
        """Return a VisualContext populated with scoreboard fields.

        Pipeline:
        1) Schedule sparse Quicksilver Gemini board referee (non-blocking)
        2) Local engine tokens (Paddle if healthy, else EasyOCR)
        3) Prefer VLM result when present; large-digit pair over badge double-counts
        4) Temporal stabilizer
        """
        if ctx is None:
            ctx = VisualContext()
        if ctx.game_category != GameCategory.FOOTBALL:
            return ctx
        if frame is None or getattr(frame, "size", 0) == 0:
            return ctx

        # Guard: blank / uniform frames have no scoreboard. Do not merge stale VLM
        # or held stabilizer lock into an empty frame (prevents inventing 0-7 Q1).
        try:
            if len(frame.shape) == 3 and frame.shape[2] >= 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame
            if gray.size > 0 and float(gray.std()) < 1.0:
                return ctx
        except Exception:
            pass

        # Smarter DeepSeek board cadence (does not block) — not every frame
        try:
            from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

            gst = None
            try:
                gst = getattr(ctx.game_state, "value", None) or str(ctx.game_state or "")
            except Exception:
                gst = None
            get_scoreboard_vlm().schedule(
                frame,
                game_state=gst,
                reason="tick",
                game_profile=getattr(ctx, "game_profile", None),
                game_title=getattr(ctx, "game_title", None),
            )
        except Exception as e:
            log.debug("scoreboard VLM schedule: %s", e)

        # Resolve scoreboard orientation: by convention the AWAY team is on the
        # LEFT and the HOME team on the RIGHT. Some broadcasts or pause menus
        # flip this. Accept a context field, env override, or fall back to the
        # standard convention.
        import os as _os_ocr

        _ocr_on = bool(allow_ocr) or _os_ocr.environ.get("QORESENCE_EASY_OCR", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
        if _ocr_on:
            try:
                from qoresence.graphs.look_gate import permit_ocr_look

                if not permit_ocr_look():
                    _ocr_on = False
            except Exception:
                pass
        # Heavy OCR (Paddle/EasyOCR) is opt-in. Running it on this tick blocks
        # the streamer subscriber path — LIVE freezes, age_s climbs, rebind loop.
        # Engine warmup is kicked once from __init__, never from this hot path.
        env_home_left = _os_ocr.environ.get("QORESENCE_SCOREBOARD_HOME_LEFT", "").strip().lower()
        home_left: bool
        if env_home_left in {"1", "true", "yes", "on"}:
            home_left = True
        elif env_home_left in {"0", "false", "no", "off"}:
            home_left = False
        elif ctx is not None and ctx.home_left is not None:
            home_left = ctx.home_left
        else:
            home_left = False

        tokens: list[_Token] = []
        if _ocr_on:
            tokens = self._ocr_tokens(frame, profile=getattr(ctx, "game_profile", None))
        parsed: dict[str, Any] = {}
        local_hud: tuple[int, int] | None = None
        if not tokens:
            try:
                from qoresence.vision.local_hud_digits import read_score_pair

                local_hud = read_score_pair(frame, getattr(ctx, "game_profile", None))
            except Exception:
                local_hud = None
            # Do NOT copy local_hud into parsed. HUD may corroborate a seeing-path
            # mint but must not source the board when VLM get_last() is None.
        if tokens:
            joined = " ".join(t.text for t in tokens).upper()
            is_paused = any(
                k in joined for k in ("PAUSED", "RESUME", "INSTANT REPLAY", "RETURN TO HUB")
            )
            parsed = self._parse(tokens, home_left=home_left)
            big = self._parse_large_score_pair(tokens, home_left=home_left)
            if big is not None:
                # Pause-menu 20|0 helper. Do not replace a team-anchored MNP/Madden
                # board with the far-right yard line (21-7 vs 21-37).
                team_locked = bool(parsed.get("home_team_raw") and parsed.get("away_team_raw"))
                have_pair = parsed.get("home_score") is not None and parsed.get("away_score") is not None
                if not (team_locked and have_pair):
                    parsed["home_score"], parsed["away_score"] = big
                    if is_paused:
                        log.debug("scoreboard pause-menu large pair %s-%s", big[0], big[1])

        local_board = local_hud is not None or (
            bool(tokens)
            and parsed.get("home_score") is not None
            and parsed.get("away_score") is not None
        )

        # Merge VLM referee (higher trust for gaming fonts)
        vlm_scores = False
        try:
            from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

            vlm = get_scoreboard_vlm().get_last()
        except Exception:
            vlm = None
        if vlm and not local_board and not _vlm_board_grounded(vlm):
            # Bare scores with no wordmarks/clock invented this morning's 3-2.
            # Grounded gameplay Gemini may still lock when HUD blobs miss.
            # Keep visible_control so picture HID can still mint from this tick.
            _vc_only = vlm.get("visible_control") if isinstance(vlm, dict) else None
            vlm = None
            if isinstance(_vc_only, dict) and (_vc_only.get("button") or _vc_only.get("glyph")):
                vlm = {"visible_control": _vc_only}
        if vlm:
            try:
                from qoresence.monitor.frame_hub import get_latest_stamp
                from qoresence.vision.picture_hid_ticket import try_mint_picture_hid_from_context
                from qoresence.vision.scoreboard_vlm import (
                    SCOREBOARD_MODEL,
                    infer_vlm_source,
                )

                stamp = get_latest_stamp() or {}
                try:
                    _gst = getattr(ctx.game_state, "value", None) or str(ctx.game_state or "")
                except Exception:
                    _gst = ""
                _vlm_ref = get_scoreboard_vlm()
                _hid_model = str(getattr(_vlm_ref, "model", "") or SCOREBOARD_MODEL)
                try_mint_picture_hid_from_context(
                    {
                        "game_state": _gst,
                        "game_profile": getattr(ctx, "game_profile", None),
                        "visible_control": vlm.get("visible_control"),
                    },
                    frame_seq=stamp.get("seq"),
                    clock_ns=int(stamp.get("clock_ns") or 0),
                    source=infer_vlm_source(
                        _hid_model, str(getattr(_vlm_ref, "base_url", "") or "")
                    ),
                    model=_hid_model,
                )
            except Exception:
                pass
        if vlm and (vlm.get("home_score") is not None or vlm.get("away_score") is not None):
            # Only merge when VLM actually read a board — never wipe a good
            # lock with a later None-None (transition frames / blur).
            vlm_has_board = vlm.get("home_score") is not None and vlm.get("away_score") is not None

            # VLM can also report scoreboard orientation (home team on left).
            vlm_home_left = vlm.get("home_left")
            if vlm_home_left is not None:
                home_left = bool(vlm_home_left)

            for k in (
                "home_score",
                "away_score",
                "quarter",
                "down",
                "yards_to_go",
                "play_clock",
                "clock_seconds",
            ):
                if vlm.get(k) is None:
                    continue
                if k in ("home_score", "away_score"):
                    if vlm_has_board:
                        parsed[k] = vlm[k]
                elif parsed.get(k) is None:
                    parsed[k] = vlm[k]
            if vlm_has_board:
                vlm_scores = True
                try:
                    from qoresence.profiles.cfb27_product import (
                        identity_compatible,
                        vlm_home_away_names,
                    )

                    nh, na = vlm_home_away_names(vlm)
                    if getattr(ctx, "score_vlm_locked", False) and not identity_compatible(
                        getattr(ctx, "home_team", None),
                        getattr(ctx, "away_team", None),
                        nh,
                        na,
                        profile=getattr(ctx, "game_profile", None),
                    ):
                        # Ticker / other-game pair — keep the held lock
                        vlm_scores = False
                        parsed.pop("home_score", None)
                        parsed.pop("away_score", None)
                except Exception:
                    pass

        if not parsed:
            # No OCR/VLM this frame — never publish held stabilizer digits without
            # a seeing-path ticket. Glass stays dark by spine honesty (null scores).
            return ctx

        gst_now = _game_state_token(ctx)
        if gst_now in _LOADING_STATES:
            try:
                from qoresence.vision.confirm_ticket import get_ticket_book

                get_ticket_book().mark_identity_stale()
            except Exception:
                pass

        # Stabilize scores so one bad frame cannot flip 17-17 → 17-2
        raw_h, raw_a = parsed.get("home_score"), parsed.get("away_score")
        stab = FootballScoreboardExtractor._stabilizer
        seeing_path_minted_this_frame = False
        if stab is not None and (raw_h is not None or raw_a is not None):
            if (
                vlm_scores
                and (local_board or _vlm_board_grounded(vlm))
                and _may_mint_lock(ctx, vlm)
                and not _ScoreStabilizer._looks_suspicious_pair((raw_h, raw_a))
            ):
                # Vision referee is trusted — force lock after a single coherent pair
                stab._stable = (int(raw_h), int(raw_a))
                stab._recent.clear()
                stab._recent.append((int(raw_h), int(raw_a)))
                sh, sa = stab._stable
                # Fail-closed: score_vlm_locked only after ConfirmTicket mint succeeds.
                locked_ok = False
                try:
                    import time as _time_ticket

                    from qoresence.monitor.frame_hub import get_latest_stamp
                    from qoresence.vision.confirm_ticket import (
                        get_ticket_book,
                        mint_confirm_ticket,
                        resolve_session_id,
                    )

                    stamp = {}
                    try:
                        stamp = get_latest_stamp() or {}
                    except Exception:
                        stamp = {}

                    def _ti(v: Any) -> int | None:
                        try:
                            return int(v) if v is not None and v != "" else None
                        except (TypeError, ValueError):
                            return None

                    # Resolve model and source from VLM referee or context
                    from qoresence.vision.scoreboard_vlm import (
                        get_scoreboard_vlm,
                        infer_vlm_source,
                    )

                    vlm_model = None
                    vlm_base = ""
                    try:
                        _ref = get_scoreboard_vlm()
                        vlm_model = _ref.model
                        vlm_base = str(_ref.base_url or "")
                    except Exception:
                        pass
                    model_str = str(
                        vlm_model
                        or getattr(ctx, "model", "")
                        or "qwen3.7-flash"
                    )
                    source_str = infer_vlm_source(model_str, vlm_base)

                    # Apply team identity early so home_team/away_team are available for ticket
                    try:
                        from qoresence.profiles.team_identity import apply_identity_to_context
                        apply_identity_to_context(ctx, parsed)
                    except Exception:
                        pass

                    book = get_ticket_book()
                    home_team_now = str(getattr(ctx, "home_team", "") or "").strip()
                    away_team_now = str(getattr(ctx, "away_team", "") or "").strip()
                    refuse = garbage_lock_reason(
                        home=int(sh),
                        away=int(sa),
                        home_team=home_team_now,
                        away_team=away_team_now,
                        game_state=_game_state_token(ctx),
                        book=book,
                    )
                    if refuse:
                        log.info(
                            "scoreboard refuse lock %s-%s (%s) %s-%s",
                            sh,
                            sa,
                            refuse,
                            home_team_now,
                            away_team_now,
                        )
                        ctx.score_vlm_locked = False
                        try:
                            from qoresence.graphs.refuse_chain import apply_refuse
                            from qoresence.graphs.ticket_provenance import record_refuse
                            from qoresence.vision.board_why import refuse_to_board_why

                            why = refuse_to_board_why(refuse, _game_state_token(ctx))
                            sid = str(getattr(ctx, "session_id", "") or "")
                            record_refuse(why, session_id=sid)
                            apply_refuse(why, session_id=sid)
                        except Exception:
                            pass
                    else:
                        last_before = book.latest()
                        ticket = mint_confirm_ticket(
                            session_id=resolve_session_id(
                                str(getattr(ctx, "session_id", "") or "")
                            ),
                            clock_ns=int(stamp.get("clock_ns") or _time_ticket.monotonic_ns()),
                            home_score=int(sh),
                            away_score=int(sa),
                            model=model_str,
                            source=source_str,
                            frame_seq=_ti(stamp.get("seq")),
                            crop_hash=str(getattr(ctx, "frame_hash", "") or ""),
                            quarter=_ti(parsed.get("quarter")),
                            down=_ti(parsed.get("down")),
                            home_team=home_team_now,
                            away_team=away_team_now,
                            book=book,
                        )
                        reused = (
                            last_before is not None
                            and ticket.ticket_id == last_before.ticket_id
                        )
                        try:
                            from qoresence.graphs.look_gate import (
                                mint_hold_drops_lock,
                                permit_confirm_mint,
                            )

                            if not permit_confirm_mint(reuse=reused):
                                if mint_hold_drops_lock() or not reused:
                                    ctx.score_vlm_locked = False
                                    locked_ok = False
                                    ticket = None  # type: ignore[assignment]
                                else:
                                    last = book.latest()
                                    if last is None:
                                        ctx.score_vlm_locked = False
                                        locked_ok = False
                                        ticket = None  # type: ignore[assignment]
                                    else:
                                        ticket = last
                        except Exception:
                            pass
                        if ticket is not None:
                            book.put(ticket, home_team=home_team_now, away_team=away_team_now)
                            try:
                                from qoresence.graphs.crop_evidence import record_lock
                                from qoresence.vision.scorebug_crops import (
                                    primary_scorebug_crop,
                                    scorebug_crops_for_profile,
                                )

                                prof = str(getattr(ctx, "game_profile", "") or "")
                                bands = scorebug_crops_for_profile(prof)
                                record_lock(
                                    prof,
                                    crop=list(primary_scorebug_crop(prof)),
                                    bands=bands,
                                    ticket_id=ticket.ticket_id,
                                    clock_ns=int(ticket.clock_ns),
                                    session_id=str(ticket.session_id or ""),
                                    crop_hash=str(ticket.crop_hash or ""),
                                    frame_seq=ticket.frame_seq,
                                )
                            except Exception:
                                pass
                            ctx.confirm_ticket_id = ticket.ticket_id
                            if isinstance(ctx.details, dict):
                                ctx.details["confirm_ticket"] = ticket.to_dict()
                            ctx.score_vlm_locked = True
                            locked_ok = True
                            log.info(
                                "scoreboard VLM lock %s-%s ticket=%s",
                                sh,
                                sa,
                                ticket.ticket_id,
                            )
                except Exception as e:
                    log.warning("confirm ticket mint failed — refuse score_vlm_locked: %s", e)
                    ctx.score_vlm_locked = False
                    locked_ok = False
                if not locked_ok:
                    # Unlicensed → do not serialize digits. Glass stays dark.
                    sh, sa = None, None
                    seeing_path_minted_this_frame = False
                else:
                    seeing_path_minted_this_frame = True
            else:
                sh, sa = stab.update(raw_h, raw_a)
            
            # Only write stabilized scores if seeing-path minted this frame
            if seeing_path_minted_this_frame:
                if sh is not None:
                    parsed["home_score"] = sh
                else:
                    parsed.pop("home_score", None)
                if sa is not None:
                    parsed["away_score"] = sa
                else:
                    parsed.pop("away_score", None)
            else:
                # No seeing-path ticket → clear scores
                parsed.pop("home_score", None)
                parsed.pop("away_score", None)
            if (raw_h, raw_a) != (sh, sa):
                log.debug(
                    "scoreboard raw %s-%s stabilized to %s-%s",
                    raw_h,
                    raw_a,
                    sh,
                    sa,
                )
        else:
            # No stabilizer or no score candidates → never publish held lock
            parsed.pop("home_score", None)
            parsed.pop("away_score", None)

        # Only write scores to ctx if seeing-path minted this frame
        if seeing_path_minted_this_frame:
            if parsed.get("home_score") is not None:
                ctx.home_score = parsed["home_score"]
            if parsed.get("away_score") is not None:
                ctx.away_score = parsed["away_score"]
        else:
            # Unlicensed → clear ctx scores
            ctx.home_score = None
            ctx.away_score = None
            ctx.score_vlm_locked = False
        if parsed.get("quarter") is not None:
            ctx.quarter = parsed["quarter"]
        if parsed.get("clock_seconds") is not None:
            ctx.clock_seconds = parsed["clock_seconds"]
        if parsed.get("down") is not None:
            ctx.down = parsed["down"]
        if parsed.get("yards_to_go") is not None:
            ctx.yards_to_go = parsed["yards_to_go"]
        if parsed.get("play_clock") is not None:
            ctx.play_clock = parsed["play_clock"]
        if parsed.get("down_distance_text"):
            ctx.down_distance_text = parsed["down_distance_text"]
        if parsed.get("home_team_raw"):
            ctx.home_team_raw = str(parsed["home_team_raw"])
        if parsed.get("away_team_raw"):
            ctx.away_team_raw = str(parsed["away_team_raw"])
        ctx.home_left = home_left
        if vlm:
            for k in (
                "left_team",
                "left_color",
                "left_logo",
                "right_team",
                "right_color",
                "right_logo",
            ):
                if vlm.get(k):
                    parsed[k] = vlm[k]
            if vlm.get("home_left") is not None:
                parsed["home_left"] = bool(vlm.get("home_left"))
        try:
            from qoresence.profiles.team_identity import apply_identity_to_context

            apply_identity_to_context(ctx, parsed)
        except Exception:
            pass
        try:
            from qoresence.profiles.nfl_roster import apply_roster_to_context

            apply_roster_to_context(ctx, parsed)
        except Exception:
            pass
        return ctx

    @staticmethod
    def _parse_large_score_pair(
        tokens: list[_Token], home_left: bool = False
    ) -> tuple[int, int] | None:
        """Pick two largest pure digit boxes left/right — CFB pause menu 20 | 0."""
        digitish: list[tuple[float, float, int, float]] = []  # (area, x, val, conf)
        for t in tokens:
            m = re.fullmatch(r"\d{1,2}", t.text.strip())
            if not m:
                continue
            val = int(m.group(0))
            if val > 99:
                continue
            # Prefer taller/wider boxes (score digits) over tiny badges
            area = max(0.01, float(getattr(t, "area", 0.0) or 0.0))
            if area < 0.002 and t.conf < 0.7:
                continue
            digitish.append((area, t.x, val, t.conf))
        if len(digitish) < 2:
            return None
        # Two largest digit boxes, then left/right. A far-right badge must not
        # become the right edge of a top-4 span (that returned None on 20|0).
        digitish.sort(key=lambda z: (-z[0], -z[3]))
        two = list(digitish[:2])
        two.sort(key=lambda z: z[1])
        left, right = two[0], two[1]
        if abs(left[1] - right[1]) < 0.08:
            return None
        if left[2] == right[2] and right[0] < left[0] * 0.35:
            for cand in digitish:
                if cand[1] > left[1] + 0.08 and cand[2] != left[2]:
                    right = cand if cand[1] > left[1] else right
                    break
        pair = (right[2], left[2])

        # Orient (home, away) according to which side the home team is on.
        if home_left:
            pair = (pair[1], pair[0])
        return pair

    def _ocr_tokens(self, frame: np.ndarray, profile: str | None = None) -> list[_Token]:
        """OCR scoreboard regions via pluggable engine (profile-aware crops)."""
        from qoresence.vision.scoreboard_ocr_engine import get_scoreboard_engine
        from qoresence.vision.scorebug_crops import scorebug_crops_for_profile

        h, w = frame.shape[:2]
        # CFB: red/blue bar just above the ticker (y > 0.93).
        # Madden: white full-width HUD strip (y≈0.9375–1.00) from preexisting frames.
        crops_frac = scorebug_crops_for_profile(profile)
        eng = get_scoreboard_engine()
        if not eng.is_ready():
            eng.start_warmup()
            return []

        tokens: list[_Token] = []
        for x1f, x2f, y1f, y2f in crops_frac:
            x1, x2 = int(w * x1f), int(w * x2f)
            y1, y2 = int(h * y1f), int(h * y2f)
            if y2 <= y1 or x2 <= x1:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            # Run on color crop (Paddle) + high-contrast gray (helps both)
            variants = [crop]
            try:
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                _, b1 = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
                variants.append(cv2.cvtColor(b1, cv2.COLOR_GRAY2BGR))
            except Exception:
                pass

            for variant in variants:
                try:
                    boxes = eng.read_boxes(variant)
                except Exception as e:
                    log.debug("scoreboard engine read failed: %s", e)
                    continue
                for b in boxes:
                    area = float(getattr(b, "w", 0.0) or 0.0) * float(getattr(b, "h", 0.0) or 0.0)
                    tokens.append(
                        _Token(
                            text=str(b.text).strip(),
                            x=float(b.x),
                            y=float(b.y),
                            conf=float(b.conf),
                            area=area,
                        )
                    )

        tokens = self._dedupe_tokens(tokens)
        tokens.sort(key=lambda t: (round(t.y, 1), t.x))
        if tokens:
            log.debug(
                "scoreboard tokens [%s]: %s",
                getattr(eng, "name", "?"),
                [(round(t.conf, 2), round(t.x, 2), t.text) for t in tokens[:16]],
            )
        return tokens

    @staticmethod
    def _dedupe_tokens(tokens: list[_Token]) -> list[_Token]:
        if not tokens:
            return []
        out: list[_Token] = []
        for t in sorted(tokens, key=lambda z: -z.conf):
            dup = False
            for u in out:
                if t.text == u.text and abs(t.x - u.x) < 0.08 and abs(t.y - u.y) < 0.12:
                    dup = True
                    break
            if not dup:
                out.append(t)
        return out

    def _parse(self, tokens: list[_Token], home_left: bool = False) -> dict[str, Any]:
        """Parse sorted OCR tokens into football fields."""
        parsed: dict[str, Any] = {}

        # Keep tokens in the scoreboard band, drop overlay/ticker rows.
        # Thin Madden / MNP strips put glyphs on the crop edge (y < 0.20).
        band = [t for t in tokens if 0.20 <= t.y <= 0.85]
        if not band:
            band = list(tokens)
        if not band:
            return parsed

        # Tight cluster: don't glue team names onto score digits (HOME+31, 38+AWAY)
        clusters = self._cluster_tokens(band, x_threshold=0.045, y_threshold=0.10)

        # Identify teams and numeric clusters, splitting "5 LOUISVILLE"-style ranks.
        team_clusters: list[_Cluster] = []
        numeric_clusters: list[_Cluster] = []
        for c in clusters:
            text = c.text
            has_alpha = bool(re.search(r"[a-zA-Z]{2,}", text))
            has_digit = bool(re.search(r"\d", text))
            if has_alpha and not has_digit:
                # Quarter words like "Ist" (OCR for 1st) are not teams.
                if re.match(r"^\d(?:st|nd|rd|th)$", _normalize_quarter_word(text), re.IGNORECASE):
                    numeric_clusters.append(c)
                else:
                    team_clusters.append(c)
            elif has_digit and not has_alpha:
                numeric_clusters.append(c)
            elif has_alpha and has_digit:
                if re.match(r"^\d(?:st|nd|rd|th)$", text, re.IGNORECASE):
                    numeric_clusters.append(c)
                    continue
                # Mixed: split rank+team OR peel score digits off team names
                rank_team = re.match(r"^(\d+)\s+([A-Za-z].*)$", text)
                team_score = re.match(r"^([A-Za-z][A-Za-z\s]+?)\s+(\d{1,2})$", text)
                score_team = re.match(r"^(\d{1,2})\s+([A-Za-z].*)$", text)
                if (
                    rank_team
                    and int(rank_team.group(1)) <= 25
                    and not re.search(r"\d{2}", rank_team.group(1))
                ):
                    # "5 LOUISVILLE" ranking — keep team only
                    team_clusters.append(
                        _Cluster(text=rank_team.group(2), x=c.x, y=c.y, conf=c.conf)
                    )
                elif team_score:
                    # "HOME 31" / "FSU 31"
                    team_clusters.append(
                        _Cluster(text=team_score.group(1).strip(), x=c.x - 0.02, y=c.y, conf=c.conf)
                    )
                    numeric_clusters.append(
                        _Cluster(text=team_score.group(2), x=c.x + 0.02, y=c.y, conf=c.conf)
                    )
                elif score_team and int(score_team.group(1)) >= 7:
                    # "31 HOME" or "38 LOUISVILLE"
                    numeric_clusters.append(
                        _Cluster(text=score_team.group(1), x=c.x - 0.02, y=c.y, conf=c.conf)
                    )
                    team_clusters.append(
                        _Cluster(text=score_team.group(2).strip(), x=c.x + 0.02, y=c.y, conf=c.conf)
                    )
                else:
                    # Peel any standalone 1–2 digit as possible score
                    for m in re.finditer(r"\b(\d{1,2})\b", text):
                        numeric_clusters.append(
                            _Cluster(text=m.group(1), x=c.x, y=c.y, conf=c.conf * 0.9)
                        )
                    letters = re.sub(r"\d+", "", text).strip()
                    if len(letters) >= 2:
                        team_clusters.append(_Cluster(text=letters, x=c.x, y=c.y, conf=c.conf))

        # Quarter: standalone down suffix token not followed by '&'.
        quarter_cluster = self._find_quarter(clusters, numeric_clusters)
        if quarter_cluster:
            q = self._extract_quarter(quarter_cluster.text)
            if q:
                parsed["quarter"] = q

        # Down/distance.
        down_cluster = self._find_down_distance(clusters)
        if down_cluster:
            m = re.search(
                r"(\d)\s*(?:st|nd|rd|th)\s*(?:&|and)\s*(\d+)", down_cluster.text, re.IGNORECASE
            )
            if m:
                parsed["down"] = int(m.group(1))
                parsed["yards_to_go"] = int(m.group(2))
                parsed["down_distance_text"] = f"{m.group(1)}st & {m.group(2)}"

        # Clock in center.
        for c in numeric_clusters:
            if 0.40 <= c.x <= 0.60:
                clock = _normalize_clock(c.text)
                if clock is not None:
                    parsed["clock_seconds"] = clock
                    break

        # Play clock: small two-digit number right of clock.
        for c in numeric_clusters:
            val = self._parse_int(c.text)
            if val is not None and 10 <= val <= 40 and 0.55 <= c.x <= 0.65:
                parsed["play_clock"] = val
                break

        # Prefer explicit "17-17" / "17–17" / "17 17" pair patterns from OCR text
        left_team = min((c for c in team_clusters), key=lambda c: c.x, default=None)
        right_team = max((c for c in team_clusters), key=lambda c: c.x, default=None)
        if left_team or right_team:
            left_txt = left_team.text if left_team else None
            right_txt = right_team.text if right_team else None
            if home_left:
                parsed["home_team_raw"] = left_txt
                parsed["away_team_raw"] = right_txt
            else:
                parsed["away_team_raw"] = left_txt
                parsed["home_team_raw"] = right_txt

        pair = self._find_score_pair_text(clusters, home_left=home_left)
        if pair is not None:
            parsed["home_score"] = pair[0]
            parsed["away_score"] = pair[1]
            return parsed

        # Scores: left-of-center (away) and right-of-center (home).
        # Use team positions to anchor.

        def _is_score_candidate(c: _Cluster) -> bool:
            val = self._parse_int(c.text)
            if val is None:
                return False
            # Single-digit 1–4 near center often quarter/down — deprioritize later
            # Exclude clock/play-clock/quarter/down tokens already consumed.
            if (
                quarter_cluster
                and abs(c.x - quarter_cluster.x) < 0.08
                and abs(c.y - quarter_cluster.y) < 0.10
            ):
                return False
            if (
                down_cluster
                and abs(c.x - down_cluster.x) < 0.15
                and abs(c.y - down_cluster.y) < 0.15
            ):
                return False
            if parsed.get("clock_seconds") and abs(c.x - 0.50) < 0.10 and _normalize_clock(c.text):
                return False
            if parsed.get("play_clock") and 0.55 <= c.x <= 0.65 and val == parsed["play_clock"]:
                return False
            return True

        candidates = [c for c in numeric_clusters if _is_score_candidate(c)]

        # Determine the team row y for vertical consistency (use median to ignore noise).
        if team_clusters:
            ys = sorted(c.y for c in team_clusters)
            team_row_y = ys[len(ys) // 2]
        else:
            team_row_y = 0.5

        def _near_team_row(c: _Cluster) -> bool:
            return abs(c.y - team_row_y) < 0.15

        def _team_adjacent_rank(c: _Cluster) -> bool:
            """A small number immediately beside a team name is likely a rank, not a score."""
            val = self._parse_int(c.text)
            if val is None or val > 30:
                return False
            for team in team_clusters:
                letters = re.sub(r"[^A-Za-z]", "", team.text)
                # NFL / Madden abbrevs (NO, CLE, KC) sit next to scores, not AP ranks.
                if len(letters) <= 3:
                    continue
                # Rank is usually LEFT of team name (e.g. "5 LOUISVILLE")
                if 0 < (team.x - c.x) < 0.14 and abs(c.y - team.y) < 0.10:
                    return True
            return False

        candidates = [c for c in candidates if _near_team_row(c) and not _team_adjacent_rank(c)]

        home_score: int | None = None
        away_score: int | None = None

        def _neighbor_score(team: _Cluster, cands: list[_Cluster]) -> int | None:
            """Digit hugging a club token — not the far-right yard line."""
            near: list[tuple[float, int]] = []
            for c in cands:
                if abs(c.y - team.y) > 0.12:
                    continue
                dx = abs(c.x - team.x)
                if dx < 0.02 or dx > 0.18:
                    continue
                val = self._parse_int(c.text)
                if val is None or val > 99:
                    continue
                near.append((dx, val))
            if not near:
                return None
            near.sort(key=lambda t: t[0])
            return near[0][1]

        # MNP / broadcast bar: NO 21 … 7 CLE … 2ND … 37. Both clubs sit left;
        # the rightmost integer is field position. Prefer digits hugging teams.
        if left_team and right_team and left_team is not right_team:
            away_n = _neighbor_score(left_team, candidates)
            home_n = _neighbor_score(right_team, candidates)
            if away_n is not None and home_n is not None and away_n != home_n:
                away_score, home_score = away_n, home_n

        def _best_score(cands: list[_Cluster], prefer_right: bool) -> int | None:
            """Prefer higher-confidence, multi-digit scores over flaky single digits."""
            if not cands:
                return None
            scored: list[tuple[float, int, _Cluster]] = []
            for c in cands:
                v = self._parse_int(c.text)
                if v is None or v > 99:
                    continue
                # Weight: confidence + bonus for 2-digit + mild position preference
                w = float(c.conf)
                if v >= 10:
                    w += 0.55  # strong preference for real late-game scores (31, 38, …)
                elif v >= 7:
                    w += 0.2
                if v == 0:
                    w += 0.05
                # Single digit 1–4 is often down/quarter noise
                if 1 <= v <= 4:
                    w -= 0.45
                scored.append((w, v, c))
            if not scored:
                return None
            scored.sort(key=lambda t: (-t[0], t[2].x if prefer_right else -t[2].x))
            return scored[0][1]

        # --- Primary: multi-digit scores in left/right halves (CFB 27) ---
        # 31-38 style: both ≥10, opposite sides of center — ignore team anchors.
        multi_left = [
            c
            for c in candidates
            if c.x < 0.45
            and (self._parse_int(c.text) or -1) >= 7
            and not (0.40 <= c.x <= 0.60 and _normalize_clock(c.text))
        ]
        multi_right = [
            c
            for c in candidates
            if c.x > 0.55
            and (self._parse_int(c.text) or -1) >= 7
            and not (0.40 <= c.x <= 0.60 and _normalize_clock(c.text))
        ]
        if multi_left and multi_right and (away_score is None or home_score is None):
            away_score = _best_score(multi_left, prefer_right=False)
            home_score = _best_score(multi_right, prefer_right=True)

        # Team-anchored fallback (left-of-center is away, right-of-center is home)
        if away_score is None and left_team:
            left_candidates = [c for c in candidates if left_team.x < c.x < 0.48]
            away_score = _best_score(left_candidates, prefer_right=False)

        if home_score is None and right_team:
            right_candidates = [c for c in candidates if 0.52 < c.x < right_team.x]
            home_score = _best_score(right_candidates, prefer_right=True)

        # Fallback to leftmost/rightmost remaining candidates in the team row.
        if away_score is None and candidates:
            left_pool = [c for c in candidates if c.x < 0.48]
            away_score = _best_score(left_pool, prefer_right=False)
        if home_score is None and candidates:
            right_pool = [c for c in candidates if c.x > 0.52]
            home_score = _best_score(right_pool, prefer_right=True)

        # Hard-reject asymmetric garbage at parse time (before stabilizer lock-in)
        if home_score is not None and away_score is not None:
            if _ScoreStabilizer._looks_suspicious_pair((home_score, away_score)):
                log.debug(
                    "scoreboard parse drop suspicious pair %s-%s",
                    home_score,
                    away_score,
                )
                # Prefer dropping the tiny side (usually quarter/down leak)
                if home_score <= 4 and away_score >= 7:
                    home_score = None
                elif away_score <= 4 and home_score >= 7:
                    away_score = None
                else:
                    home_score, away_score = None, None

        # Orient (home, away) according to which side the home team is on.
        # The parser above treats left-of-center as away and right-of-center as home;
        # home_left=True means the HOME team is actually on the left.
        if home_left:
            home_score, away_score = away_score, home_score

        # If only one side found, leave the other unset (don't invent 0)
        if home_score is not None:
            parsed["home_score"] = home_score
        if away_score is not None:
            parsed["away_score"] = away_score

        return parsed

    @staticmethod
    def _find_score_pair_text(
        clusters: list[_Cluster], home_left: bool = False
    ) -> tuple[int, int] | None:
        """Detect explicit scoreline patterns like 17-17, 17–17, 21 14."""
        for c in clusters:
            text = c.text.replace("–", "-").replace("—", "-").replace(":", "-")
            m = re.search(r"\b(\d{1,2})\s*[-/]\s*(\d{1,2})\b", text)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 0 <= a <= 99 and 0 <= b <= 99:
                    if _ScoreStabilizer._looks_suspicious_pair((a, b)):
                        continue
                    # left-of-center is away, right-of-center is home
                    pair = (b, a)
                    if home_left:
                        pair = (a, b)
                    return pair
        # Prefer left-half + right-half multi-digit pair (true scorebug), not
        # adjacent (31, 2) where 2 is quarter in the center.
        nums: list[tuple[int, float, float]] = []
        for c in clusters:
            if re.fullmatch(r"\d{1,2}", c.text.strip()):
                v = int(c.text.strip())
                if 0 <= v <= 99:
                    nums.append((v, c.x, c.y))
        left = [n for n in nums if n[1] < 0.42 and n[0] >= 7]
        right = [n for n in nums if n[1] > 0.58 and n[0] >= 7]
        if left and right:
            # Highest value confidence proxy: prefer >=10, then rightmost/leftmost
            lh = max(left, key=lambda n: (n[0] >= 10, n[0], -abs(n[1] - 0.25)))
            rh = max(right, key=lambda n: (n[0] >= 10, n[0], -abs(n[1] - 0.75)))
            # MNP / Madden: far-right 1–50 is field position (A 22, ▼ 37), not home.
            if rh[1] > 0.78 and lh[1] < 0.45:
                return None
            # left-of-center is away, right-of-center is home
            pair = (rh[0], lh[0])
            if home_left:
                pair = (lh[0], rh[0])
            if not _ScoreStabilizer._looks_suspicious_pair(pair):
                return pair
        return None

    @staticmethod
    def _cluster_tokens(
        tokens: list[_Token], x_threshold: float = 0.06, y_threshold: float = 0.10
    ) -> list[_Cluster]:
        """Merge tokens that are close in 2D into single text clusters."""
        if not tokens:
            return []
        sorted_tokens = sorted(tokens, key=lambda t: (round(t.y, 1), t.x))
        clusters: list[_Cluster] = []
        current: list[_Token] = [sorted_tokens[0]]
        for tok in sorted_tokens[1:]:
            last = current[-1]
            x_gap = tok.x - last.x
            y_gap = abs(tok.y - last.y)
            # Only merge left-to-right within the same vertical band.
            if 0 <= x_gap <= x_threshold and y_gap <= y_threshold:
                current.append(tok)
            else:
                clusters.append(FootballScoreboardExtractor._make_cluster(current))
                current = [tok]
        clusters.append(FootballScoreboardExtractor._make_cluster(current))
        return clusters

    @staticmethod
    def _make_cluster(tokens: list[_Token]) -> _Cluster:
        text = " ".join(t.text for t in tokens)
        x = sum(t.x for t in tokens) / len(tokens)
        y = sum(t.y for t in tokens) / len(tokens)
        conf = sum(t.conf for t in tokens) / len(tokens)
        return _Cluster(text=text, x=x, y=y, conf=conf)

    def _find_quarter(
        self, clusters: list[_Cluster], numeric_clusters: list[_Cluster]
    ) -> _Cluster | None:
        """Find a standalone quarter token (1st/2nd/3rd/4th) in the center-left."""
        for c in clusters:
            text = _normalize_quarter_word(c.text)
            if re.match(r"^\d(?:st|nd|rd|th)$", text, re.IGNORECASE):
                # Ensure this isn't the down part of a down-distance cluster.
                if not re.search(r"&", c.text) and "and" not in c.text.lower():
                    # prefer center-left cluster
                    if 0.30 <= c.x <= 0.55:
                        return c
        return None

    def _find_down_distance(self, clusters: list[_Cluster]) -> _Cluster | None:
        """Find a down & distance cluster."""
        for c in clusters:
            text = _normalize_quarter_word(c.text)
            # Replace lst/Ist/Jst with 1st before regex
            text = re.sub(r"\b[ljiz]?st\b", "1st", text, flags=re.IGNORECASE)
            text = re.sub(r"\b2nd\b", "2nd", text, flags=re.IGNORECASE)
            text = re.sub(r"\b3rd\b", "3rd", text, flags=re.IGNORECASE)
            text = re.sub(r"\b4th\b", "4th", text, flags=re.IGNORECASE)
            if re.search(r"\d\s*(?:st|nd|rd|th)\s*(?:&|and)\s*\d+", text, re.IGNORECASE):
                return _Cluster(text=text, x=c.x, y=c.y, conf=c.conf)
        return None

    @staticmethod
    def _extract_quarter(text: str) -> int | None:
        t = _normalize_quarter_word(text).lower().replace(" ", "")
        m = re.match(r"^(\d)(?:st|nd|rd|th)$", t)
        if m:
            return int(m.group(1))
        return None

    @staticmethod
    def _parse_int(text: str) -> int | None:
        t = _fix_digits_in(text).strip()
        t = re.sub(r"\D", "", t)
        try:
            return int(t) if t else None
        except ValueError:
            return None


def extract_football_scoreboard(
    frame: np.ndarray, ctx: VisualContext | None = None
) -> VisualContext:
    """Live entry: enqueue a frame copy and apply the last worker result.

    Heavy extract stays on ``scoreboard-lock``. Tests that need a synchronous
    read should call ``FootballScoreboardExtractor.extract`` directly.
    """
    from qoresence.vision.scoreboard_lock import offer_scoreboard_frame

    return offer_scoreboard_frame(frame, ctx)
