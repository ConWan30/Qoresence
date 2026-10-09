"""Rebuild a local scorebug template pack from hand-verified labelled frames.

Usage (after a game patch or to add digits/skins):

    python -m qoresence.vision.local_scorebug.build_pack \\
        --labels qoresence/vision/local_scorebug/labels/madden27_box_labels.json \\
        --frames /path/to/frames \\
        --out qoresence/vision/local_scorebug/packs/madden27_standard_v1.npz

Only frames whose label says ``"skin": "madden_standard"`` are used, and only
fields that were verified by eye (``left``/``right`` scores, ``quarter``,
``clock``). A label of ``null`` means "no readable value" and is skipped; a
clock of ``"?"`` means "could not be verified" and is skipped.

Templates are per-label means of real glyphs cut by the reader's own geometry.
Nothing is synthesised: a digit that never appears in the labels gets no
template, so the reader can only blank on it.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from qoresence.vision.local_scorebug.profile import PROFILES, ScorebugProfile
from qoresence.vision.local_scorebug.reader import ScorebugReader, TemplatePack, _shift


def load_labels(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        data = {"frames": data}
    return data


def _unit(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-6 else v


def _mean_unit(vs: list[np.ndarray]) -> np.ndarray:
    return _unit(np.mean(np.stack(vs), 0).astype(np.float32))


def build_pack(
    rows: list[dict[str, Any]],
    frames_root: str | Path,
    profile: ScorebugProfile,
    *,
    exclude_clips: set[str] | None = None,
    source_note: str = "",
) -> tuple[TemplatePack, dict[str, Any]]:
    """Return (pack, report). ``exclude_clips`` supports leave-one-clip-out evals."""
    root = Path(frames_root)
    exclude = exclude_clips or set()
    use = [
        r
        for r in rows
        if r.get("skin") == profile.skin_label
        and r.get("clip") not in exclude
        and r.get("train", True)
    ]
    images: list[tuple[dict[str, Any], np.ndarray]] = []
    for r in use:
        img = cv2.imread(str(root / r["frame"]))
        if img is not None:
            images.append((r, img))
    if not images:
        raise ValueError("no labelled standard-skin frames found")

    # Pass 1: logo template at zero offset, so the reader can anchor.
    lx1, lx2, ly1, ly2 = profile.logo
    tmp = ScorebugReader(
        profile,
        TemplatePack(logo=np.zeros((ly2 - ly1, lx2 - lx1), np.float32), groups={}),
    )
    bands = []
    for r, img in images:
        band, why = tmp.reference_band(img)
        if band is not None:
            bands.append((r, band))
    logos = [
        cv2.cvtColor(tmp._crop(b, profile.logo), cv2.COLOR_BGR2GRAY).astype(np.float32)
        for _, b in bands
    ]
    pack = TemplatePack(logo=np.mean(np.stack(logos), 0), groups={})
    reader = ScorebugReader(profile, pack)
    # Pass 2: anchor offsets, logo re-averaged at those offsets.
    anchored = []
    for r, b in bands:
        score, (dx, dy) = reader.find_anchor(b)
        if score >= profile.min_logo_ncc:
            anchored.append((r, b, dx, dy))
    logos = [
        cv2.cvtColor(reader._crop(b, _shift(profile.logo, dx, dy)), cv2.COLOR_BGR2GRAY).astype(
            np.float32
        )
        for _, b, dx, dy in anchored
    ]
    pack = TemplatePack(logo=np.mean(np.stack(logos), 0), groups={})
    reader = ScorebugReader(profile, pack)

    score_recs: dict[str, list[np.ndarray]] = defaultdict(list)
    hole_recs: dict[str, Counter[str]] = defaultdict(Counter)
    clock_recs: dict[str, list[np.ndarray]] = defaultdict(list)
    clock_skipped = 0
    quarter_recs: dict[str, list[np.ndarray]] = defaultdict(list)
    seg_mismatch = 0
    for r, b, dx, dy in anchored:
        for side, box in (("left", profile.left_score), ("right", profile.right_score)):
            lab = r.get(side)
            if lab is None:
                continue
            slot = reader._crop(b, _shift(box, dx, dy))
            if slot is None:
                continue
            glyphs, why, _ = reader.score_glyphs(slot)
            text = str(int(lab))
            if glyphs is None or len(glyphs) != len(text):
                seg_mismatch += 1
                continue
            for ch, (v, holes) in zip(text, glyphs, strict=True):
                score_recs[ch].append(v)
                hole_recs[ch][holes] += 1
        clock = r.get("clock")
        if clock not in (None, "?"):
            mm, ss = str(clock).split(":")
            vecs, _why = reader.clock_glyphs(b, dx, dy)
            if vecs is not None and len(mm) == 1 and len(ss) == 2:
                for ch, v in zip(mm + ss, vecs, strict=True):
                    clock_recs[ch].append(v)
            elif len(mm) == 1 and len(ss) == 2:
                clock_skipped += 1
        q = r.get("quarter")
        if q:
            best = None
            for jj in (-1, 0, 1):
                v = reader.quarter_vector(b, dx + jj, dy)
                if v is None:
                    continue
                key = (
                    float(v @ quarter_recs[q][0])
                    if quarter_recs.get(q)
                    else (1.0 if jj == 0 else 0.0)
                )
                if best is None or key > best[0]:
                    best = (key, v)
            if best is not None:
                quarter_recs[str(q)].append(best[1])

    groups: dict[str, dict[str, np.ndarray]] = {"score": {}, "clock": {}, "quarter": {}}
    for ch, vs in score_recs.items():
        groups["score"][ch] = _mean_unit(vs)[None, :]
    for ch, vs in clock_recs.items():
        groups["clock"][ch] = _mean_unit(vs)[None, :]
    for q, vs in quarter_recs.items():
        groups["quarter"][q] = _mean_unit(vs)[None, :]

    counts = {
        "score": {k: len(v) for k, v in sorted(score_recs.items())},
        "clock": {k: len(v) for k, v in sorted(clock_recs.items())},
        "quarter": {k: len(v) for k, v in sorted(quarter_recs.items())},
    }
    meta = {
        "profile_id": profile.profile_id,
        "layout_version": profile.layout_version,
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frames_used": len(anchored),
        "clips": sorted({str(r.get("clip")) for r, *_ in anchored}),
        "glyph_counts": counts,
        # Diagnostics only: check profile.score_hole_rules still hold after a rebuild.
        "score_hole_counts": {ch: dict(sorted(c.items())) for ch, c in sorted(hole_recs.items())},
        "missing_score_digits": [d for d in "0123456789" if d not in score_recs],
        "source": source_note,
    }
    report = {"seg_mismatch": seg_mismatch, "clock_skipped": clock_skipped, **meta}
    return TemplatePack(logo=pack.logo, groups=groups, meta=meta), report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--labels", required=True)
    ap.add_argument("--frames", required=True, help="folder holding the labelled frame images")
    ap.add_argument("--out", required=True)
    ap.add_argument("--profile", default="madden27_standard", choices=sorted(PROFILES))
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv)
    data = load_labels(args.labels)
    pack, report = build_pack(
        data["frames"], args.frames, PROFILES[args.profile], source_note=args.note
    )
    pack.save(args.out)
    sys.stdout.write(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
