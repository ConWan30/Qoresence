"""Local scoreboard OCR + parsing for NCAA football frames.

Uses EasyOCR on a bottom-center crop and extracts score, quarter, clock,
down/distance, and play-clock from the HUD. No cloud VLM calls.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from qoresence.vision.visual_context import GameCategory, VisualContext

log = logging.getLogger(__name__)


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
    mapping = str.maketrans({
        "J": "1", "j": "1", "I": "1", "i": "1", "l": "1", "L": "1",
        "O": "0", "o": "0", "S": "5", "s": "5", "B": "8", "b": "8",
        "G": "6", "g": "6", "Z": "2", "z": "2", "T": "7", "t": "7",
        "|": "", ":": "",
    })
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


class FootballScoreboardExtractor:
    """Extract football scoreboard fields from a BGR frame."""

    _reader: Any | None = None

    def __init__(self) -> None:
        self._easyocr_available = False
        try:
            import easyocr  # noqa: F401
            self._easyocr_available = True
        except Exception:
            log.warning("easyocr not installed; scoreboard extraction disabled")

    @classmethod
    def _get_reader(cls) -> Any:
        if cls._reader is None:
            import easyocr
            log.info("Loading EasyOCR reader for scoreboard extraction...")
            cls._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return cls._reader

    def extract(self, frame: np.ndarray, ctx: VisualContext | None = None) -> VisualContext:
        """Return a VisualContext populated with scoreboard fields."""
        if ctx is None:
            ctx = VisualContext()
        if not self._easyocr_available or ctx.game_category != GameCategory.FOOTBALL:
            return ctx

        tokens = self._ocr_tokens(frame)
        if not tokens:
            return ctx

        parsed = self._parse(tokens)
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
        """OCR the bottom-center scoreboard region and return tokens."""
        h, w = frame.shape[:2]
        # Bottom-center scoreboard crop, ignoring far left/right ticker edges.
        x1 = int(w * 0.28)
        x2 = int(w * 0.72)
        y1 = int(h * 0.83)
        y2 = int(h * 0.97)
        if y1 < 0 or y2 <= y1 or x2 <= x1:
            return []

        crop = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        # White text on dark background is the dominant scoreboard pattern.
        _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        scaled = cv2.resize(binary, (crop.shape[1] * 3, crop.shape[0] * 3), interpolation=cv2.INTER_CUBIC)

        try:
            reader = self._get_reader()
            results = reader.readtext(scaled, detail=1)
        except Exception as e:
            log.debug(f"Scoreboard OCR failed: {e}")
            return []

        tokens: list[_Token] = []
        for bbox, text, conf in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            cx = (min(xs) + max(xs)) / 2 / scaled.shape[1]
            cy = (min(ys) + max(ys)) / 2 / scaled.shape[0]
            tokens.append(_Token(text=text.strip(), x=cx, y=cy, conf=float(conf)))

        # Sort top-to-bottom, then left-to-right.
        tokens.sort(key=lambda t: (round(t.y, 1), t.x))
        return tokens

    def _parse(self, tokens: list[_Token]) -> dict[str, Any]:
        """Parse sorted OCR tokens into football fields."""
        parsed: dict[str, Any] = {}

        # Keep tokens in the scoreboard band, drop overlay/ticker rows.
        band = [t for t in tokens if 0.20 <= t.y <= 0.85]
        if not band:
            return parsed

        clusters = self._cluster_tokens(band, x_threshold=0.10, y_threshold=0.12)

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
                # Mixed, e.g. "5 LOUISVILLE" (rank + team) or "1st" (quarter).
                rank_team = re.match(r"^(\d+)\s+([A-Za-z].*)$", text)
                if rank_team:
                    # Keep the team name; discard the leading rank number from scoring.
                    team_clusters.append(_Cluster(text=rank_team.group(2), x=c.x, y=c.y, conf=c.conf))
                else:
                    numeric_clusters.append(c)

        # Quarter: standalone down suffix token not followed by '&'.
        quarter_cluster = self._find_quarter(clusters, numeric_clusters)
        if quarter_cluster:
            q = self._extract_quarter(quarter_cluster.text)
            if q:
                parsed["quarter"] = q

        # Down/distance.
        down_cluster = self._find_down_distance(clusters)
        if down_cluster:
            m = re.search(r"(\d)\s*(?:st|nd|rd|th)\s*(?:&|and)\s*(\d+)", down_cluster.text, re.IGNORECASE)
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

        # Scores: left-of-center (home) and right-of-center (away).
        # Use team positions to anchor.
        left_team = min((c for c in team_clusters), key=lambda c: c.x, default=None)
        right_team = max((c for c in team_clusters), key=lambda c: c.x, default=None)

        def _is_score_candidate(c: _Cluster) -> bool:
            val = self._parse_int(c.text)
            if val is None:
                return False
            # Exclude clock/play-clock/quarter/down tokens already consumed.
            if quarter_cluster and abs(c.x - quarter_cluster.x) < 0.08 and abs(c.y - quarter_cluster.y) < 0.10:
                return False
            if down_cluster and abs(c.x - down_cluster.x) < 0.15 and abs(c.y - down_cluster.y) < 0.15:
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
                if abs(c.x - team.x) < 0.12 and abs(c.y - team.y) < 0.10:
                    return True
            return False

        candidates = [c for c in candidates if _near_team_row(c) and not _team_adjacent_rank(c)]

        home_score: int | None = None
        away_score: int | None = None

        if left_team:
            left_candidates = [c for c in candidates if left_team.x < c.x < 0.45]
            if left_candidates:
                home_score = self._parse_int(min(left_candidates, key=lambda c: c.x).text)

        if right_team:
            right_candidates = [c for c in candidates if 0.55 < c.x < right_team.x]
            if right_candidates:
                away_score = self._parse_int(max(right_candidates, key=lambda c: c.x).text)

        # Fallback to leftmost/rightmost remaining candidates in the team row.
        if home_score is None and candidates:
            left_c = min([c for c in candidates if c.x < 0.45], key=lambda c: c.x, default=None)
            if left_c:
                home_score = self._parse_int(left_c.text)
        if away_score is None and candidates:
            right_c = max([c for c in candidates if c.x > 0.55], key=lambda c: c.x, default=None)
            if right_c:
                away_score = self._parse_int(right_c.text)

        if home_score is not None:
            parsed["home_score"] = home_score
        if away_score is not None:
            parsed["away_score"] = away_score

        return parsed

    @staticmethod
    def _cluster_tokens(tokens: list[_Token], x_threshold: float = 0.06, y_threshold: float = 0.10) -> list[_Cluster]:
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

    def _find_quarter(self, clusters: list[_Cluster], numeric_clusters: list[_Cluster]) -> _Cluster | None:
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


def extract_football_scoreboard(frame: np.ndarray, ctx: VisualContext | None = None) -> VisualContext:
    """Convenience entry point."""
    return FootballScoreboardExtractor().extract(frame, ctx)
