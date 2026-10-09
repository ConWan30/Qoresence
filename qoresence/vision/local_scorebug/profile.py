"""Scorebug layout profiles for the local reader.

A profile pins one game + one scorebug skin + one layout version. Geometry is
stored as fractions of the full frame so the same profile serves 640x360,
720p and 1080p captures: the reader cuts the bottom band by fraction and
rescales it to the profile's reference size before any glyph work.

Only one profile ships in phase 1: the standard Madden NFL 27 bottom strip.
Anything that does not match it (dark primetime skin, College Football,
a patched layout) fails the anchor check and the reader stays blank.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACK_DIR = Path(__file__).resolve().parent / "packs"

Box = tuple[int, int, int, int]  # x1, x2, y1, y2 in reference pixels


@dataclass(frozen=True)
class GlyphGate:
    """Per-glyph acceptance: absolute NCC floor and margin over the runner-up."""

    min_score: float
    min_margin: float


@dataclass(frozen=True)
class ScorebugProfile:
    profile_id: str
    game: str
    skin: str
    skin_label: str  # value of "skin" in label files for this profile
    layout_version: str
    pack_file: str
    ref_w: int
    ref_h: int
    # Bottom band that holds the whole strip, as fractions of frame height.
    band_y0: float
    band_y1: float
    # Reference-pixel boxes (full-frame coordinates at ref_w x ref_h).
    logo: Box
    score_panel: Box
    left_score: Box
    right_score: Box
    clock_box: Box
    clock_text: Box  # region holding "M:SS" (white digits on the dark box)
    clock_glyph_size: tuple[int, int]
    clock_ink_frac: float  # ink = value > frac * 98th percentile of the region
    clock_min_peak: float
    clock_split_w: int
    clock_digit_w: tuple[int, int]
    quarter: Box
    anchor_search_px: int
    min_logo_ncc: float
    min_panel_white: float
    max_clock_box_border_v: float
    score_gate: GlyphGate
    clock_gate: GlyphGate
    quarter_gate: GlyphGate
    # Score glyph geometry at reference scale (Madden digits are ~10-11 px).
    score_glyph_min_h: int
    score_glyph_max_h: int
    score_glyph_min_area: int
    score_glyph_split_w: int
    score_glyph_max_w: int
    score_pair_max_gap: int
    max_slot_ink: float
    max_aspect_error: float
    # Required hole signature (see glyphs.hole_signature) for digits an unseen
    # glyph could be mistaken for. Any glyph with two or more holes always blanks.
    score_hole_rules: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def frac(self, box: Box) -> tuple[float, float, float, float]:
        """Return a reference-pixel box as (x1, x2, y1, y2) frame fractions."""
        x1, x2, y1, y2 = box
        return (x1 / self.ref_w, x2 / self.ref_w, y1 / self.ref_h, y2 / self.ref_h)

    @property
    def pack_path(self) -> Path:
        return PACK_DIR / self.pack_file


# Measured on 640x360 HDMI captures of Madden NFL 27 (Sept 2026 sessions).
# Fractions: score slots x 0.344-0.384 / 0.402-0.444, y 0.950-0.992;
# strip y 0.939-1.0; clock box x 0.669-0.756. See docs in README.md here.
MADDEN27_STANDARD = ScorebugProfile(
    profile_id="madden27_standard",
    game="madden_27",
    skin="standard_bottom_strip",
    skin_label="madden_standard",
    layout_version="madden27-standard-v1",
    pack_file="madden27_standard_v1.npz",
    ref_w=640,
    ref_h=360,
    band_y0=330 / 360,
    band_y1=1.0,
    logo=(8, 80, 340, 358),
    score_panel=(200, 300, 341, 357),
    left_score=(220, 246, 342, 357),
    right_score=(257, 284, 342, 357),
    clock_box=(428, 484, 341, 356),
    clock_text=(447, 480, 344, 353),
    clock_glyph_size=(6, 9),
    clock_ink_frac=0.65,
    clock_min_peak=80.0,
    clock_split_w=10,
    clock_digit_w=(2, 8),
    quarter=(430, 447, 344, 353),
    anchor_search_px=3,
    min_logo_ncc=0.90,
    min_panel_white=0.45,
    max_clock_box_border_v=70.0,
    # Gates were set by leave-one-clip-out sweeps on the box clips: with any one
    # digit's template removed, every glyph of that digit must blank. Score
    # impostors topped out at NCC 0.64 (gate 0.70); clock impostors at 0.88
    # (gate 0.93). See qoresence/vision/local_scorebug/README.md.
    score_gate=GlyphGate(min_score=0.70, min_margin=0.08),
    clock_gate=GlyphGate(min_score=0.93, min_margin=0.06),
    quarter_gate=GlyphGate(min_score=0.85, min_margin=0.05),
    score_glyph_min_h=8,
    score_glyph_max_h=14,
    score_glyph_min_area=12,
    score_glyph_split_w=13,
    score_glyph_max_w=26,
    score_pair_max_gap=4,
    max_slot_ink=0.50,
    max_aspect_error=0.03,
    # Held in every training session: 0 always showed one hole across the
    # middle, 9 one hole above it, 3 none. A Madden 8 (no template yet) is two
    # loops, so the digits it resembles most must keep their usual topology.
    score_hole_rules=(("0", ("1c",)), ("3", ("0",)), ("9", ("1u",))),
)

PROFILES: dict[str, ScorebugProfile] = {MADDEN27_STANDARD.profile_id: MADDEN27_STANDARD}
