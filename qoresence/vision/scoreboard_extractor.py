"""Local scoreboard OCR + parsing for NCAA football frames.

Uses EasyOCR on a bottom-center crop and extracts score, quarter, clock,
down/distance, and play-clock from the HUD. No cloud VLM calls.

Score updates are **stabilized** (temporal consensus + plausible deltas) so a
single misread like 17-2 cannot wipe a real 17-17.
"""

from __future__ import annotations

import logging
import re
import time
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

    def update(
        self, home: int | None, away: int | None
    ) -> tuple[int | None, int | None]:
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
        if (h >= 10 and 1 <= a <= 4) or (a >= 10 and 1 <= h <= 4):
            return True
        if (h >= 7 and 1 <= a <= 4) or (a >= 7 and 1 <= h <= 4):
            return True
        # Huge imbalance with tiny side (e.g. 28-1 mid-game OCR glitch)
        if min(h, a) <= 3 and max(h, a) >= 14:
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
    """Extract football scoreboard fields from a BGR frame."""

    _reader: Any | None = None
    # Process-wide stabilizer so multi-instance extractors share consensus
    _stabilizer: _ScoreStabilizer | None = None
    # Background EasyOCR warm-up — never block the visual loop on first load
    _reader_loading: bool = False
    _reader_failed: bool = False
    _load_lock: Any | None = None

    def __init__(self) -> None:
        self._easyocr_available = False
        try:
            import easyocr  # noqa: F401
            import threading

            self._easyocr_available = True
            if FootballScoreboardExtractor._load_lock is None:
                FootballScoreboardExtractor._load_lock = threading.Lock()
        except Exception:
            log.warning("easyocr not installed; scoreboard extraction disabled")
        if FootballScoreboardExtractor._stabilizer is None:
            FootballScoreboardExtractor._stabilizer = _ScoreStabilizer(window=6, need=2)

    @classmethod
    def _ensure_reader_async(cls) -> None:
        """Kick off EasyOCR load on a daemon thread if not already started."""
        if cls._reader is not None or cls._reader_failed or cls._reader_loading:
            return
        import threading

        lock = cls._load_lock
        if lock is None:
            lock = threading.Lock()
            cls._load_lock = lock
        with lock:
            if cls._reader is not None or cls._reader_failed or cls._reader_loading:
                return
            cls._reader_loading = True

        def _load() -> None:
            try:
                import easyocr

                log.info("Loading EasyOCR reader for scoreboard extraction (background)...")
                cls._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
                log.info("EasyOCR reader ready for scoreboard extraction")
            except Exception as e:
                cls._reader_failed = True
                log.warning("EasyOCR reader load failed: %s", e)
            finally:
                cls._reader_loading = False

        threading.Thread(target=_load, name="easyocr-warmup", daemon=True).start()

    @classmethod
    def _get_reader(cls) -> Any | None:
        """Return reader if ready; never block the visual thread on cold start."""
        if cls._reader is not None:
            return cls._reader
        if cls._reader_failed:
            return None
        cls._ensure_reader_async()
        return None  # still loading — skip this frame

    def extract(self, frame: np.ndarray, ctx: VisualContext | None = None) -> VisualContext:
        """Return a VisualContext populated with scoreboard fields.

        If EasyOCR is still loading, returns ``ctx`` unchanged so visual_context
        (and ClutchBot) keep flowing without multi-minute stalls.
        """
        if ctx is None:
            ctx = VisualContext()
        if not self._easyocr_available or ctx.game_category != GameCategory.FOOTBALL:
            return ctx
        if self._get_reader() is None:
            return ctx

        tokens = self._ocr_tokens(frame)
        if not tokens:
            return ctx

        parsed = self._parse(tokens)

        # Stabilize scores so one bad frame cannot flip 17-17 → 17-2
        raw_h, raw_a = parsed.get("home_score"), parsed.get("away_score")
        stab = FootballScoreboardExtractor._stabilizer
        if stab is not None and (raw_h is not None or raw_a is not None):
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
        return ctx

    def _ocr_tokens(self, frame: np.ndarray) -> list[_Token]:
        """OCR scoreboard regions and return tokens (multi-crop for CFB 27 HUD)."""
        h, w = frame.shape[:2]
        # CFB 27 scorebug is bottom-center; also try a slightly higher band.
        # Fractions of full frame (x1,x2,y1,y2)
        crops_frac = (
            (0.22, 0.78, 0.80, 0.98),  # primary bottom scorebug
            (0.28, 0.72, 0.74, 0.90),  # slightly higher (large-score layouts)
        )
        tokens: list[_Token] = []
        try:
            reader = self._get_reader()
        except Exception as e:
            log.debug(f"Scoreboard OCR reader failed: {e}")
            return []
        if reader is None:
            return []

        for x1f, x2f, y1f, y2f in crops_frac:
            x1, x2 = int(w * x1f), int(w * x2f)
            y1, y2 = int(h * y1f), int(h * y2f)
            if y2 <= y1 or x2 <= x1:
                continue
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            # Dual threshold: white-on-dark + Otsu (handles red/glass HUDs better)
            variants = []
            _, b1 = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
            variants.append(b1)
            _, b2 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(b2)
            # Also try inverted Otsu for dark text
            variants.append(cv2.bitwise_not(b2))

            for binary in variants:
                scaled = cv2.resize(
                    binary,
                    (max(1, crop.shape[1] * 3), max(1, crop.shape[0] * 3)),
                    interpolation=cv2.INTER_CUBIC,
                )
                try:
                    results = reader.readtext(scaled, detail=1)
                except Exception as e:
                    log.debug(f"Scoreboard OCR failed: {e}")
                    continue
                for bbox, text, conf in results:
                    if conf is not None and float(conf) < 0.25:
                        continue
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    # Map back to crop-normalized then full-frame-normalized x/y
                    cx_c = (min(xs) + max(xs)) / 2 / scaled.shape[1]
                    cy_c = (min(ys) + max(ys)) / 2 / scaled.shape[0]
                    cx = x1f + cx_c * (x2f - x1f)
                    cy = y1f + cy_c * (y2f - y1f)
                    # Re-normalize to crop-local 0..1 for parse band logic:
                    # keep crop-relative for _parse which expects band coords
                    tokens.append(
                        _Token(
                            text=str(text).strip(),
                            x=float(cx_c),
                            y=float(cy_c),
                            conf=float(conf),
                        )
                    )

        # Dedup similar text near same position
        tokens = self._dedupe_tokens(tokens)
        tokens.sort(key=lambda t: (round(t.y, 1), t.x))
        if tokens:
            log.debug(
                "scoreboard tokens: %s",
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

    def _parse(self, tokens: list[_Token]) -> dict[str, Any]:
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
                if rank_team and int(rank_team.group(1)) <= 25 and not re.search(
                    r"\d{2}", rank_team.group(1)
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
        pair = self._find_score_pair_text(clusters)
        if pair is not None:
            parsed["home_score"] = pair[0]
            parsed["away_score"] = pair[1]
            return parsed

        # Scores: left-of-center (home) and right-of-center (away).
        # Use team positions to anchor.
        left_team = min((c for c in team_clusters), key=lambda c: c.x, default=None)
        right_team = max((c for c in team_clusters), key=lambda c: c.x, default=None)

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
            home_score = _best_score(multi_left, prefer_right=False)
            away_score = _best_score(multi_right, prefer_right=True)

        # Team-anchored fallback
        if home_score is None and left_team:
            left_candidates = [c for c in candidates if left_team.x < c.x < 0.48]
            home_score = _best_score(left_candidates, prefer_right=False)

        if away_score is None and right_team:
            right_candidates = [c for c in candidates if 0.52 < c.x < right_team.x]
            away_score = _best_score(right_candidates, prefer_right=True)

        # Fallback to leftmost/rightmost remaining candidates in the team row.
        if home_score is None and candidates:
            left_pool = [c for c in candidates if c.x < 0.48]
            home_score = _best_score(left_pool, prefer_right=False)
        if away_score is None and candidates:
            right_pool = [c for c in candidates if c.x > 0.52]
            away_score = _best_score(right_pool, prefer_right=True)

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

        # If only one side found, leave the other unset (don't invent 0)
        if home_score is not None:
            parsed["home_score"] = home_score
        if away_score is not None:
            parsed["away_score"] = away_score

        return parsed

    @staticmethod
    def _find_score_pair_text(clusters: list[_Cluster]) -> tuple[int, int] | None:
        """Detect explicit scoreline patterns like 17-17, 17–17, 21 14."""
        for c in clusters:
            text = c.text.replace("–", "-").replace("—", "-").replace(":", "-")
            m = re.search(r"\b(\d{1,2})\s*[-/]\s*(\d{1,2})\b", text)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 0 <= a <= 99 and 0 <= b <= 99:
                    if _ScoreStabilizer._looks_suspicious_pair((a, b)):
                        continue
                    return a, b
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
