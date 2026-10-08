"""Local scorebug reader: per-frame verdicts on tiny committed fixture crops."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from qoresence.vision.local_scorebug.glyphs import dark_on_light_ink, hole_signature
from qoresence.vision.local_scorebug.profile import MADDEN27_STANDARD, GlyphGate
from qoresence.vision.local_scorebug.reader import ScorebugReader, TemplatePack, _shift
from tests.local_scorebug_helpers import band, frame_from_band

GOOD = [
    ("std_29_15_4th_2-38", (29, 15), 4, "2:38"),
    ("std_14_7_2nd_1-23", (14, 7), 2, "1:23"),
    ("std_6_0_2nd_0-50_dim", (6, 0), 2, "0:50"),
    ("std_21_24_4th_0-32", (21, 24), 4, "0:32"),
    ("std_22_7_3rd_4-00", (22, 7), 3, "4:00"),
    ("std_0_0_2nd_0-53", (0, 0), 2, "0:53"),
]


@pytest.fixture(scope="module")
def reader() -> ScorebugReader:
    return ScorebugReader()


@pytest.mark.parametrize("name,pair,quarter,clock", GOOD)
def test_reads_standard_strip(reader, name, pair, quarter, clock):
    r = reader.read(frame_from_band(name))
    assert r.ok, r.reason
    assert r.pair == pair
    assert r.quarter == quarter
    assert r.clock_text == clock
    m, s = clock.split(":")
    assert r.clock_seconds == int(m) * 60 + int(s)
    assert r.score_conf >= MADDEN27_STANDARD.score_gate.min_score
    assert r.score_margin >= MADDEN27_STANDARD.score_gate.min_margin


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
@pytest.mark.parametrize("name,pair,quarter,clock", GOOD)
def test_rois_are_fractions_same_read_at_720p_1080p(reader, size, name, pair, quarter, clock):
    r = reader.read(frame_from_band(name, size))
    assert r.ok, (size, r.reason)
    assert (r.pair, r.quarter, r.clock_text) == (pair, quarter, clock)


@pytest.mark.parametrize("size", [(960, 540), (854, 480), (1024, 576)])
@pytest.mark.parametrize("name,pair,quarter,clock", GOOD)
def test_odd_scales_read_same_or_blank(reader, size, name, pair, quarter, clock):
    """Non-integer rescales soften glyphs: the reader may blank, never misread."""
    r = reader.read(frame_from_band(name, size))
    if r.ok:
        assert (r.pair, r.quarter, r.clock_text) == (pair, quarter, clock)


@pytest.mark.parametrize(
    "name,reason",
    [
        ("dark_skin", "layout_unknown"),
        ("cfb", "layout_unknown"),
        ("no_scorebug", "layout_unknown"),
        ("std_touchdown_banner", "score_panel_covered"),
        ("std_red_clock", "clock_red"),
    ],
)
def test_unknown_skin_banner_and_red_clock_stay_blank(reader, name, reason):
    r = reader.read(frame_from_band(name))
    assert not r.ok
    assert r.reason == reason
    # Blank reads never carry digits the mint path could pick up.
    assert r.pair is None and r.quarter is None and r.clock_seconds is None


def test_wrong_aspect_or_tiny_frame_blank(reader):
    wide = np.zeros((360, 800, 3), np.uint8)
    assert reader.read(wide).reason == "frame_aspect"
    assert reader.read(np.zeros((90, 160, 3), np.uint8)).reason == "frame_too_small"
    assert reader.read(None).reason == "frame_invalid"


def test_confidence_gate_blanks(reader):
    strict = dataclasses.replace(
        MADDEN27_STANDARD, score_gate=GlyphGate(min_score=0.999, min_margin=0.08)
    )
    r = ScorebugReader(strict, reader.pack).read(frame_from_band("std_29_15_4th_2-38"))
    assert not r.ok and r.reason == "score_unsure"
    assert r.pair is None


def test_margin_gate_blanks(reader):
    strict = dataclasses.replace(
        MADDEN27_STANDARD, score_gate=GlyphGate(min_score=0.70, min_margin=0.99)
    )
    r = ScorebugReader(strict, reader.pack).read(frame_from_band("std_14_7_2nd_1-23"))
    assert not r.ok and r.reason == "score_unsure"


def test_clock_gate_blanks_and_keeps_digits_out(reader):
    strict = dataclasses.replace(
        MADDEN27_STANDARD, clock_gate=GlyphGate(min_score=0.999, min_margin=0.06)
    )
    r = ScorebugReader(strict, reader.pack).read(frame_from_band("std_14_7_2nd_1-23"))
    assert not r.ok and r.reason == "clock_unsure"
    assert r.pair is None  # partial pair only in detail, never on the read
    assert r.detail.get("partial_pair") == [14, 7]


def _pack_without(pack: TemplatePack, group: str, label: str) -> TemplatePack:
    groups = {k: dict(v) for k, v in pack.groups.items()}
    groups[group].pop(label)
    return TemplatePack(logo=pack.logo, groups=groups, meta=dict(pack.meta))


@pytest.mark.parametrize(
    "name,digit",
    [
        ("std_29_15_4th_2-38", "9"),
        ("std_14_7_2nd_1-23", "4"),
        ("std_6_0_2nd_0-50_dim", "6"),
        ("std_21_24_4th_0-32", "2"),
        ("std_0_0_2nd_0-53", "0"),
    ],
)
def test_unlearned_score_digit_blanks(reader, name, digit):
    """A digit with no template (today: 8) must blank, never read as a neighbour."""
    r = ScorebugReader(MADDEN27_STANDARD, _pack_without(reader.pack, "score", digit)).read(
        frame_from_band(name)
    )
    assert not r.ok
    assert r.reason in {"score_unsure", "score_glyph_holes"}


@pytest.mark.parametrize("name,digit", [("std_29_15_4th_2-38", "3"), ("std_22_7_3rd_4-00", "4")])
def test_unlearned_clock_digit_blanks(reader, name, digit):
    r = ScorebugReader(MADDEN27_STANDARD, _pack_without(reader.pack, "clock", digit)).read(
        frame_from_band(name)
    )
    assert not r.ok and r.reason == "clock_unsure"


def test_unlearned_quarter_blanks(reader):
    r = ScorebugReader(MADDEN27_STANDARD, _pack_without(reader.pack, "quarter", "4th")).read(
        frame_from_band("std_29_15_4th_2-38")
    )
    assert not r.ok and r.reason == "quarter_unsure"


def test_shipped_pack_has_no_fabricated_eight(reader):
    assert "8" not in reader.pack.groups["score"]
    assert reader.pack.meta["missing_score_digits"] == ["8"]
    assert "ot" not in reader.pack.groups["quarter"]
    assert reader.model_id.startswith("local_scorebug_v1:madden27-standard-v1:")


def _right_zero_glyph(reader: ScorebugReader, b: np.ndarray):
    rb, _ = reader.reference_band(frame_from_band(b))
    _, (dx, dy), _ = reader.check_layout(rb)
    x1, x2, y1, y2 = _shift(MADDEN27_STANDARD.right_score, dx, dy)
    top = reader._band_top()
    glyphs, why, boxes = reader.score_glyphs(rb[y1 - top : y2 - top, x1:x2])
    assert why == "ok" and len(boxes) == 1
    x, y, w, h = boxes[0]
    return (x1 + x, y1 - top + y, w, h)


@pytest.mark.parametrize("fill_rows", [(5,), (5, 6)])
def test_eight_shaped_glyph_blanks(reader, fill_rows):
    """Probe, not a template: close the right '0' into an 8 (two holes, or one off-centre).

    At 640x360 an 8 is a dark oval like 0; the hole-topology guard must blank it.
    """
    b = band("std_0_0_2nd_0-53").copy()
    gx, gy, gw, gh = _right_zero_glyph(reader, b)
    glyph = b[gy : gy + gh, gx : gx + gw]
    ink = dark_on_light_ink(glyph) > 0
    colour = np.median(glyph[ink], axis=0).astype(np.uint8)
    for row in fill_rows:
        line = glyph[row]
        line[~ink[row]] = colour
    assert hole_signature(dark_on_light_ink(b[gy : gy + gh, gx : gx + gw])) in {"2+", "1u"}
    r = reader.read(frame_from_band(b))
    assert not r.ok
    assert r.reason in {"score_glyph_holes", "score_unsure"}


def test_hole_signature_shapes():
    ring = np.zeros((10, 8), np.uint8)
    ring[1:9, 1:7] = 255
    ring[3:7, 3:5] = 0
    assert hole_signature(ring) == "1c"
    eight = ring.copy()
    eight[5, 3:5] = 255
    assert hole_signature(eight) == "2+"
    top_only = ring.copy()
    top_only[5:7, 3:5] = 255
    assert hole_signature(top_only) == "1u"
    solid = np.full((10, 8), 255, np.uint8)
    assert hole_signature(solid) == "0"


def test_pack_round_trip(tmp_path, reader):
    p = tmp_path / "pack.npz"
    reader.pack.save(p)
    again = TemplatePack.load(p)
    assert again.sha16 == reader.pack.sha16
    assert again.labels("score") == reader.pack.labels("score")
    r = ScorebugReader(MADDEN27_STANDARD, again).read(frame_from_band("std_14_7_2nd_1-23"))
    assert r.ok and r.pair == (14, 7)
