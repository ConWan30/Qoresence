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
        # Kick preferred engine warm-up without blocking
        try:
            from qoresence.vision.scoreboard_ocr_engine import get_scoreboard_engine

            eng = get_scoreboard_engine()
            eng.start_warmup()
            FootballScoreboardExtractor._engine_name = getattr(eng, "name", None)
        except Exception as e:
            log.debug("scoreboard engine init: %s", e)

    def extract(self, frame: np.ndarray, ctx: VisualContext | None = None) -> VisualContext:
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

        # Smarter Gemini board cadence (does not block) — not every frame
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
            )
        except Exception as e:
            log.debug("scoreboard VLM schedule: %s", e)

        # Resolve scoreboard orientation: by convention the AWAY team is on the
        # LEFT and the HOME team on the RIGHT. Some broadcasts or pause menus
        # flip this. Accept a context field, env override, or fall back to the
        # standard convention.
        import os as _os_ocr

        _ocr_on = _os_ocr.environ.get("QORESENCE_EASY_OCR", "0").strip().lower() in {
            "1",
            "true",
            "yes",
        }
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
        if tokens:
            joined = " ".join(t.text for t in tokens).upper()
            is_paused = any(
                k in joined for k in ("PAUSED", "RESUME", "INSTANT REPLAY", "RETURN TO HUB")
            )
            parsed = self._parse(tokens, home_left=home_left)
            big = self._parse_large_score_pair(tokens, home_left=home_left)
            if big is not None:
                parsed["home_score"], parsed["away_score"] = big
                if is_paused:
                    log.debug("scoreboard pause-menu large pair %s-%s", big[0], big[1])

        # Merge VLM referee (higher trust for gaming fonts)
        vlm_scores = False
        try:
            from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

            vlm = get_scoreboard_vlm().get_last()
        except Exception:
            vlm = None
        if vlm:
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
            # No OCR/VLM this frame — still publish a held stabilizer lock so a
            # null VLM (transition / blur) does not wipe a good score lock
            # (invariant #5). update(None, None) returns the held lock unchanged.
            stab = FootballScoreboardExtractor._stabilizer
            if stab is not None:
                sh, sa = stab.update(None, None)
                if sh is not None:
                    ctx.home_score = sh
                if sa is not None:
                    ctx.away_score = sa
            return ctx

        # Stabilize scores so one bad frame cannot flip 17-17 → 17-2
        raw_h, raw_a = parsed.get("home_score"), parsed.get("away_score")
        stab = FootballScoreboardExtractor._stabilizer
        if stab is not None and (raw_h is not None or raw_a is not None):
            if vlm_scores and not _ScoreStabilizer._looks_suspicious_pair((raw_h, raw_a)):
                # Vision referee is trusted — force lock after a single coherent pair
                stab._stable = (int(raw_h), int(raw_a))
                stab._recent.clear()
                stab._recent.append((int(raw_h), int(raw_a)))
                sh, sa = stab._stable
                ctx.score_vlm_locked = True
                try:
                    import time as _time_ticket

                    from qoresence.monitor.frame_hub import get_latest_stamp
                    from qoresence.vision.confirm_ticket import get_ticket_book, mint_confirm_ticket

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

                    ticket = mint_confirm_ticket(
                        session_id=str(getattr(ctx, "session_id", "") or ""),
                        clock_ns=int(stamp.get("clock_ns") or _time_ticket.monotonic_ns()),
                        home_score=int(sh),
                        away_score=int(sa),
                        model=str(getattr(ctx, "model", "") or "gemini-3.5-flash-lite"),
                        frame_seq=_ti(stamp.get("seq")),
                        crop_hash=str(getattr(ctx, "frame_hash", "") or ""),
                        quarter=_ti(parsed.get("quarter")),
                        down=_ti(parsed.get("down")),
                    )
                    get_ticket_book().put(ticket)
                    ctx.confirm_ticket_id = ticket.ticket_id
                    if isinstance(ctx.details, dict):
                        ctx.details["confirm_ticket"] = ticket.to_dict()
                    log.info(
                        "scoreboard VLM lock %s-%s ticket=%s",
                        sh,
                        sa,
                        ticket.ticket_id,
                    )
                except Exception as e:
                    log.debug("confirm ticket mint skipped: %s", e)
                    log.info("scoreboard VLM lock %s-%s", sh, sa)
            else:
                sh, sa = stab.update(raw_h, raw_a)
            if sh is not None:
                parsed["home_score"] = sh
            else:
                parsed.pop("home_score", None)
            if sa is not None:
                parsed["away_score"] = sa
            else:
                parsed.pop("away_score", None)
            if (raw_h, raw_a) != (sh, sa):
                log.debug(
                    "scoreboard raw %s-%s stabilized to %s-%s",
                    raw_h,
                    raw_a,
                    sh,
                    sa,
                )
        elif stab is not None:
            # No score candidates this frame (e.g. partial VLM with only
            # quarter, OCR empty) — publish held lock so a null/partial VLM
            # does not wipe a good score lock (invariant #5).
            sh, sa = stab.update(None, None)
            if sh is not None:
                parsed["home_score"] = sh
            if sa is not None:
                parsed["away_score"] = sa

        if parsed.get("home_score") is not None:
            ctx.home_score = parsed["home_score"]
        if parsed.get("away_score") is not None:
            ctx.away_score = parsed["away_score"]
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
        # Top by area, then take leftmost and rightmost among top-4
        digitish.sort(key=lambda z: (-z[0], -z[3]))
        top = digitish[:4]
        top.sort(key=lambda z: z[1])  # by x
        left = top[0]
        right = top[-1]
        if abs(left[1] - right[1]) < 0.08:
            return None
        # Reject same-digit double-count when right is a badge (tiny area, same val)
        pair = (right[2], left[2])
        if left[2] == right[2] and right[0] < left[0] * 0.35:
            # look for a zero or smaller score on right among top
            for cand in sorted(digitish, key=lambda z: z[1]):
                if cand[1] > 0.5 and cand[2] != left[2]:
                    pair = (cand[2], left[2])
                    break
            # Prefer 0 if we only see one big score left of center
            if left[1] < 0.55:
                for cand in digitish:
                    if cand[2] == 0 and cand[1] > left[1]:
                        pair = (0, left[2])
                        break

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
        band = [t for t in tokens if 0.20 <= t.y <= 0.85]
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
                # Rank is usually LEFT of team name (e.g. "5 LOUISVILLE")
                if 0 < (team.x - c.x) < 0.14 and abs(c.y - team.y) < 0.10:
                    return True
            return False

        candidates = [c for c in candidates if _near_team_row(c) and not _team_adjacent_rank(c)]

        home_score: int | None = None
        away_score: int | None = None

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
        if multi_left and multi_right:
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
    """Convenience entry point."""
    return FootballScoreboardExtractor().extract(frame, ctx)
