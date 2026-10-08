"""Keyless local scorebug reader: one frame in, a sure reading or a blank out.

Pipeline (all at the profile's reference scale):
  1. frame shape check (16:9, big enough) and bottom-band rescale;
  2. layout anchor: the MADDEN wordmark must match its template (searching a
     few pixels for capture offset), the score panel must be white and the
     clock box must be dark;
  3. score slots: dark/team-coloured ink, digit-height components, 1-2 glyphs,
     each glyph matched against Madden's own digit templates;
  4. clock (M:SS cells) and quarter (word template) from the dark clock box.

Every glyph must clear an absolute NCC floor AND a margin over the runner-up
digit. Any failed check returns a blank with a reason. No guessing: a digit
with no template (for example a Madden score "8" until one is harvested)
can only blank.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from qoresence.vision.local_scorebug.glyphs import (
    GLYPH_SIZE,
    GlyphMatch,
    column_runs,
    components,
    dark_on_light_ink,
    hole_signature,
    norm_vec,
)
from qoresence.vision.local_scorebug.profile import MADDEN27_STANDARD, Box, ScorebugProfile

READER_ID = "local_scorebug_v1"
QUARTER_WORDS = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "ot": 5}


@dataclass(frozen=True)
class FrameRead:
    """One frame's verdict. ``ok`` only when scores, clock and quarter are all sure."""

    ok: bool
    reason: str
    profile_id: str
    left_score: int | None = None
    right_score: int | None = None
    quarter: int | None = None
    clock_seconds: int | None = None
    clock_text: str | None = None
    score_conf: float | None = None
    score_margin: float | None = None
    clock_conf: float | None = None
    clock_margin: float | None = None
    quarter_conf: float | None = None
    offset: tuple[int, int] = (0, 0)
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def pair(self) -> tuple[int, int] | None:
        if self.left_score is None or self.right_score is None:
            return None
        return (self.left_score, self.right_score)


class TemplatePack:
    """Glyph templates for one profile, loaded from a small ``.npz`` data file."""

    def __init__(
        self,
        *,
        logo: np.ndarray,
        groups: dict[str, dict[str, np.ndarray]],
        meta: dict[str, Any] | None = None,
    ) -> None:
        self.logo = logo.astype(np.float32)
        self.groups = {
            g: {k: np.atleast_2d(v).astype(np.float32) for k, v in d.items()}
            for g, d in groups.items()
        }
        self.meta = dict(meta or {})
        h = hashlib.sha256()
        h.update(self.logo.tobytes())
        for g in sorted(self.groups):
            for k in sorted(self.groups[g]):
                h.update(f"{g}/{k}".encode())
                h.update(self.groups[g][k].tobytes())
        self.sha16 = h.hexdigest()[:16]

    def match_shifted(self, group: str, vecs: list[np.ndarray | None]) -> GlyphMatch | None:
        """Shift-tolerant match: each label scores its best over every shifted view."""
        tpl = self.groups.get(group) or {}
        views = [v for v in vecs if v is not None]
        if not views or not tpl:
            return None
        stack = np.stack(views)
        scored = sorted(((float(np.max(t @ stack.T)), k) for k, t in tpl.items()), reverse=True)
        best, label = scored[0]
        second = scored[1][0] if len(scored) > 1 else -1.0
        return GlyphMatch(label=label, best=best, second=second)

    def labels(self, group: str) -> list[str]:
        return sorted(self.groups.get(group, {}))

    def match(self, group: str, vec: np.ndarray | None) -> GlyphMatch | None:
        """Best label vs runner-up label (max over each label's variants)."""
        tpl = self.groups.get(group) or {}
        if vec is None or not tpl:
            return None
        scored = sorted(((float(np.max(v @ vec)), k) for k, v in tpl.items()), reverse=True)
        best, label = scored[0]
        second = scored[1][0] if len(scored) > 1 else -1.0
        return GlyphMatch(label=label, best=best, second=second)

    @classmethod
    def load(cls, path: str | Path) -> TemplatePack:
        with np.load(str(path), allow_pickle=False) as z:
            meta = json.loads(str(z["meta"])) if "meta" in z.files else {}
            groups: dict[str, dict[str, np.ndarray]] = {}
            for key in z.files:
                if "__" not in key:
                    continue
                g, label = key.split("__", 1)
                groups.setdefault(g, {})[label] = np.array(z[key])
            return cls(logo=np.array(z["logo"]), groups=groups, meta=meta)

    def save(self, path: str | Path) -> None:
        arrays: dict[str, Any] = {"logo": self.logo.astype(np.float32)}
        for g, d in self.groups.items():
            for k, v in d.items():
                arrays[f"{g}__{k}"] = v.astype(np.float32)
        arrays["meta"] = np.array(json.dumps(self.meta, sort_keys=True))
        np.savez_compressed(str(path), **arrays)


def _shift(box: Box, dx: int, dy: int) -> Box:
    x1, x2, y1, y2 = box
    return (x1 + dx, x2 + dx, y1 + dy, y2 + dy)


class ScorebugReader:
    """Stateless per-frame reader for one profile + template pack."""

    def __init__(
        self, profile: ScorebugProfile = MADDEN27_STANDARD, pack: TemplatePack | None = None
    ) -> None:
        self.profile = profile
        self.pack = pack if pack is not None else TemplatePack.load(profile.pack_path)

    @property
    def model_id(self) -> str:
        return f"{READER_ID}:{self.profile.layout_version}:{self.pack.sha16}"

    # ---- geometry -----------------------------------------------------
    def _band_top(self) -> int:
        return int(round(self.profile.ref_h * self.profile.band_y0))

    def reference_band(self, frame: np.ndarray) -> tuple[np.ndarray | None, str]:
        """Bottom band of the frame rescaled to reference pixels (rows band_top..ref_h)."""
        p = self.profile
        if frame is None or getattr(frame, "ndim", 0) != 3 or frame.shape[2] < 3:
            return None, "frame_invalid"
        h, w = int(frame.shape[0]), int(frame.shape[1])
        if w < int(0.94 * p.ref_w) or h < int(0.94 * p.ref_h):
            return None, "frame_too_small"
        aspect = (w / float(h)) / (p.ref_w / float(p.ref_h))
        if abs(aspect - 1.0) > p.max_aspect_error:
            return None, "frame_aspect"
        y0 = int(round(h * p.band_y0))
        y1 = int(round(h * p.band_y1))
        band = frame[y0:y1, :, :3]
        out_h = p.ref_h - self._band_top()
        if band.shape[0] == out_h and band.shape[1] == p.ref_w:
            return np.ascontiguousarray(band), "ok"
        interp = cv2.INTER_AREA if band.shape[1] > p.ref_w else cv2.INTER_LINEAR
        return cv2.resize(band, (p.ref_w, out_h), interpolation=interp), "ok"

    def _crop(self, band: np.ndarray, box: Box) -> np.ndarray | None:
        x1, x2, y1, y2 = box
        top = self._band_top()
        ya, yb = y1 - top, y2 - top
        if x1 < 0 or ya < 0 or x2 > band.shape[1] or yb > band.shape[0] or x2 <= x1 or yb <= ya:
            return None
        return band[ya:yb, x1:x2]

    def find_anchor(self, band: np.ndarray) -> tuple[float, tuple[int, int]]:
        """Best logo NCC within +-anchor_search_px; returns (score, (dx, dy))."""
        p = self.profile
        s = p.anchor_search_px
        x1, x2, y1, y2 = p.logo
        win = self._crop(band, (x1 - s, x2 + s, y1 - s, y2 + s))
        if win is None:
            # Search window clipped by the band edge: search what we have.
            win = self._crop(
                band, (max(0, x1 - s), x2 + s, max(self._band_top(), y1 - s), min(p.ref_h, y2 + s))
            )
            if win is None:
                return -1.0, (0, 0)
            ox = max(0, x1 - s) - (x1 - s)
            oy = max(self._band_top(), y1 - s) - (y1 - s)
        else:
            ox = oy = 0
        gray = cv2.cvtColor(win, cv2.COLOR_BGR2GRAY).astype(np.float32)
        tpl = self.pack.logo
        if gray.shape[0] < tpl.shape[0] or gray.shape[1] < tpl.shape[1]:
            return -1.0, (0, 0)
        res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
        _, best, _, loc = cv2.minMaxLoc(res)
        dx = int(loc[0]) + ox - s
        dy = int(loc[1]) + oy - s
        return float(best), (dx, dy)

    # ---- fields ---------------------------------------------------------
    def score_glyphs(
        self, slot: np.ndarray
    ) -> tuple[list[tuple[np.ndarray, str]] | None, str, list[tuple[int, int, int, int]]]:
        """(vector, hole signature) per glyph in one score slot, or (None, reason, boxes)."""
        p = self.profile
        mask = dark_on_light_ink(slot)
        if float((mask > 0).mean()) > p.max_slot_ink:
            return None, "score_slot_ink", []
        boxes = components(
            mask,
            min_h=5,
            max_h=p.score_glyph_max_h,
            min_area=p.score_glyph_min_area,
            split_w=p.score_glyph_split_w,
            max_w=p.score_glyph_max_w,
        )
        if any(w < 0 for _, _, w, _ in boxes):
            return None, "score_shape", boxes
        if not 1 <= len(boxes) <= 2:
            return None, "score_glyph_count", boxes
        for _, _, w, h in boxes:
            if h < p.score_glyph_min_h or h > p.score_glyph_max_h or w < 2:
                return None, "score_glyph_size", boxes
        if len(boxes) == 2:
            (xa, _, wa, _), (xb, _, _, _) = boxes
            if xb - (xa + wa) > p.score_pair_max_gap:
                return None, "score_glyph_gap", boxes
        out = []
        for x, y, w, h in boxes:
            glyph = mask[y : y + h, x : x + w]
            v = norm_vec(glyph, GLYPH_SIZE)
            if v is None:
                return None, "score_glyph_flat", boxes
            out.append((v, hole_signature(glyph)))
        return out, "ok", boxes

    def score_glyph_vectors(
        self, slot: np.ndarray
    ) -> tuple[list[np.ndarray] | None, str, list[tuple[int, int, int, int]]]:
        """Glyph vectors for one score slot, or (None, reason, boxes)."""
        glyphs, why, boxes = self.score_glyphs(slot)
        if glyphs is None:
            return None, why, boxes
        return [v for v, _ in glyphs], why, boxes

    def _read_score(self, band: np.ndarray, box: Box) -> tuple[int | None, str, float, float]:
        slot = self._crop(band, box)
        if slot is None:
            return None, "score_roi", 0.0, 0.0
        glyphs, why, _ = self.score_glyphs(slot)
        if glyphs is None:
            return None, why, 0.0, 0.0
        gate = self.profile.score_gate
        shapes = dict(self.profile.score_hole_rules)
        digits = ""
        conf, margin = 1.0, 1.0
        for v, holes in glyphs:
            m = self.pack.match("score", v)
            if m is None:
                return None, "score_no_templates", 0.0, 0.0
            conf, margin = min(conf, m.best), min(margin, m.margin)
            if m.best < gate.min_score or m.margin < gate.min_margin:
                return None, "score_unsure", m.best, m.margin
            # Topology guard: no trained digit has two holes, and the digits an
            # 8 resembles must show their usual hole layout.
            if holes == "2+" or (m.label in shapes and holes not in shapes[m.label]):
                return None, "score_glyph_holes", m.best, m.margin
            digits += m.label
        if len(digits) == 2 and digits[0] == "0":
            return None, "score_leading_zero", conf, margin
        return int(digits), "ok", conf, margin

    def quarter_vector(self, band: np.ndarray, dx: int, dy: int) -> np.ndarray | None:
        x1, x2, y1, y2 = self.profile.quarter
        patch = self._crop(band, (x1 + dx, x2 + dx, y1 + dy, y2 + dy))
        if patch is None:
            return None
        v = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[..., 2]
        return norm_vec(v, (x2 - x1, y2 - y1))

    def _best_jitter(self, fn: Any, group: str, dx: int, dy: int) -> GlyphMatch | None:
        """Shift-tolerant match over -1/0/+1 px horizontal jitter (quarter word)."""
        return self.pack.match_shifted(group, [fn(dx + j, dy) for j in (-1, 0, 1)])

    def clock_is_red(self, patch_bgr: np.ndarray) -> bool:
        """True when the clock digits are drawn in red (final seconds)."""
        hsv = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2HSV)
        ink = hsv[..., 2] > 90
        if not ink.any():
            return False
        return float(hsv[..., 1][ink].mean()) > 90.0

    def clock_glyphs(
        self, band: np.ndarray, dx: int, dy: int
    ) -> tuple[list[np.ndarray] | None, str]:
        """Segment "M:SS" into three digit vectors (minute, tens, ones) or blank.

        The clock font is proportional (a "1" is narrow), so digits are cut by
        ink columns rather than fixed cells: exactly digit, colon, digit, digit.
        """
        p = self.profile
        patch = self._crop(band, _shift(p.clock_text, dx, dy))
        if patch is None:
            return None, "clock_roi"
        if self.clock_is_red(patch):
            # Red final-seconds clock is blurry at 360p; red 1-vs-9 confusions
            # were seen in testing, so phase 1 never reads it.
            return None, "clock_red"
        v = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
        peak = float(np.percentile(v, 98))
        if peak < p.clock_min_peak:
            return None, "clock_missing"
        mask = (v > p.clock_ink_frac * peak).astype(np.uint8)
        runs: list[tuple[int, int]] = []
        for a, b in column_runs(mask):
            if b - a >= p.clock_split_w:
                cols = mask[:, a:b].sum(0)
                w = b - a
                lo, hi = w // 3, 2 * w // 3 + 1
                cut = a + lo + int(cols[lo:hi].argmin())
                runs += [(a, cut), (cut, b)]
            else:
                runs.append((a, b))
        if len(runs) != 4:
            # 10:00+ (two minute digits), banners, or merged glyphs: not learned.
            return None, "clock_layout"
        (ma, mb), (ca, cb), (s1a, s1b), (s2a, s2b) = runs
        if cb - ca > 3:
            return None, "clock_layout"
        rows = np.flatnonzero(mask[:, ca:cb].any(1))
        if rows.size == 0 or np.all(np.diff(rows) == 1):
            return None, "clock_colon"  # a colon is two dots, not one bar
        lo_w, hi_w = p.clock_digit_w
        vecs = []
        for a, b in ((ma, mb), (s1a, s1b), (s2a, s2b)):
            if not lo_w <= b - a <= hi_w:
                return None, "clock_glyph_size"
            vec = norm_vec(v[:, a:b], p.clock_glyph_size)
            if vec is None:
                return None, "clock_glyph_flat"
            vecs.append(vec)
        return vecs, "ok"

    def _read_clock(
        self, band: np.ndarray, dx: int, dy: int
    ) -> tuple[int | None, str | None, str, float, float]:
        vecs, why = self.clock_glyphs(band, dx, dy)
        if vecs is None:
            return None, None, why, 0.0, 0.0
        gate = self.profile.clock_gate
        digits = []
        conf, margin = 1.0, 1.0
        for vec in vecs:
            m = self.pack.match("clock", vec)
            if m is None:
                return None, None, "clock_no_templates", 0.0, 0.0
            conf, margin = min(conf, m.best), min(margin, m.margin)
            if m.best < gate.min_score or m.margin < gate.min_margin:
                return None, None, "clock_unsure", m.best, m.margin
            digits.append(m.label)
        mm, s1, s2 = (int(d) for d in digits)
        if s1 > 5:
            return None, None, "clock_impossible", conf, margin
        return mm * 60 + s1 * 10 + s2, f"{mm}:{s1}{s2}", "ok", conf, margin

    def _read_quarter(self, band: np.ndarray, dx: int, dy: int) -> tuple[int | None, str, float]:
        m = self._best_jitter(
            lambda ddx, ddy: self.quarter_vector(band, ddx, ddy), "quarter", dx, dy
        )
        if m is None:
            return None, "quarter_no_templates", 0.0
        gate = self.profile.quarter_gate
        if m.best < gate.min_score or m.margin < gate.min_margin:
            return None, "quarter_unsure", m.best
        q = QUARTER_WORDS.get(m.label.lower())
        if q is None:
            return None, "quarter_unknown", m.best
        return q, "ok", m.best

    # ---- main -----------------------------------------------------------
    def check_layout(self, band: np.ndarray) -> tuple[str, tuple[int, int], dict[str, float]]:
        p = self.profile
        logo_ncc, (dx, dy) = self.find_anchor(band)
        info = {"logo_ncc": round(logo_ncc, 4)}
        if logo_ncc < p.min_logo_ncc:
            return "layout_unknown", (dx, dy), info
        panel = self._crop(band, _shift(p.score_panel, dx, dy))
        if panel is None:
            return "layout_unknown", (dx, dy), info
        g = cv2.cvtColor(panel, cv2.COLOR_BGR2GRAY)
        s = cv2.cvtColor(panel, cv2.COLOR_BGR2HSV)[..., 1]
        white = float(((g > 170) & (s < 60)).mean())
        info["panel_white"] = round(white, 4)
        if white < p.min_panel_white:
            return "score_panel_covered", (dx, dy), info
        cb = self._crop(band, _shift(p.clock_box, dx, dy))
        if cb is None:
            return "layout_unknown", (dx, dy), info
        v = cv2.cvtColor(cb, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
        border = float(np.concatenate([v[:2].ravel(), v[-2:].ravel()]).mean())
        info["clock_border_v"] = round(border, 2)
        if border > p.max_clock_box_border_v:
            return "clock_box_missing", (dx, dy), info
        return "ok", (dx, dy), info

    def read(self, frame: np.ndarray) -> FrameRead:
        pid = self.profile.profile_id
        band, why = self.reference_band(frame)
        if band is None:
            return FrameRead(ok=False, reason=why, profile_id=pid)
        why, (dx, dy), info = self.check_layout(band)
        if why != "ok":
            return FrameRead(ok=False, reason=why, profile_id=pid, offset=(dx, dy), detail=info)
        p = self.profile
        left, lwhy, lc, lm = self._read_score(band, _shift(p.left_score, dx, dy))
        right, rwhy, rc, rm = self._read_score(band, _shift(p.right_score, dx, dy))
        info.update({"left": lwhy, "right": rwhy})
        if left is None or right is None:
            reason = lwhy if left is None else rwhy
            return FrameRead(ok=False, reason=reason, profile_id=pid, offset=(dx, dy), detail=info)
        secs, text, cwhy, cc, cm = self._read_clock(band, dx, dy)
        if secs is None:
            info["partial_pair"] = [left, right]
            return FrameRead(ok=False, reason=cwhy, profile_id=pid, offset=(dx, dy), detail=info)
        q, qwhy, qc = self._read_quarter(band, dx, dy)
        if q is None:
            info["partial_pair"] = [left, right]
            info["partial_clock"] = text
            return FrameRead(ok=False, reason=qwhy, profile_id=pid, offset=(dx, dy), detail=info)
        return FrameRead(
            ok=True,
            reason="ok",
            profile_id=pid,
            left_score=left,
            right_score=right,
            quarter=q,
            clock_seconds=secs,
            clock_text=text,
            score_conf=round(min(lc, rc), 4),
            score_margin=round(min(lm, rm), 4),
            clock_conf=round(cc, 4),
            clock_margin=round(cm, 4),
            quarter_conf=round(qc, 4),
            offset=(dx, dy),
            detail=info,
        )
