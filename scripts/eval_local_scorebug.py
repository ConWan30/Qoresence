#!/usr/bin/env python3
"""Offline eval for the keyless local scorebug reader.

Frame mode (every labelled frame, one verdict each):

    python scripts/eval_local_scorebug.py \\
        --labels qoresence/vision/local_scorebug/labels/madden27_box_labels.json \\
        --frames /path/to/frames [--loco]

``--loco`` (leave-one-clip-out) rebuilds the template pack without the clip
under test, so a clip is never read with its own glyphs. Without it the
shipped pack is used (in-sample for the clips it was built from).

Clip mode (every decoded video frame through the full agreement window):

    python scripts/eval_local_scorebug.py --labels ... --frames ... \\
        --clips /path/to/clips [--clips /other/dir]

Clip truth comes from the frame labels: a video frame is scored only when the
labelled frames on both sides of it agree (same pair, or both "no score").

Counts, per clip and per clip set:
  correct  the reader answered and matched the label
  blank    the reader stayed blank (the safe answer when unsure)
  wrong    the reader answered and did not match (or answered on a frame with
           no readable score). This must be 0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from qoresence.vision.local_scorebug.agreement import AgreementConfig  # noqa: E402
from qoresence.vision.local_scorebug.build_pack import build_pack, load_labels  # noqa: E402
from qoresence.vision.local_scorebug.glyphs import dark_on_light_ink  # noqa: E402
from qoresence.vision.local_scorebug.profile import PROFILES  # noqa: E402
from qoresence.vision.local_scorebug.reader import (  # noqa: E402
    QUARTER_WORDS,
    ScorebugReader,
    TemplatePack,
    _shift,
)
from qoresence.vision.local_scorebug.service import LocalScorebugService  # noqa: E402

FRAME_TIME_OFFSET_S = -0.56  # labelled frame NNN was sampled at about (NNN - 0.56) s


def clip_set(row: dict[str, Any]) -> str:
    skin = str(row.get("skin") or "none")
    return skin


def score_frame(row: dict[str, Any], fr: Any) -> tuple[str, str]:
    """Return (kind, outcome). kind = 'score' | 'no_score'; outcome correct/blank/wrong."""
    want = (row.get("left"), row.get("right"))
    has_score = want[0] is not None and want[1] is not None
    kind = "score" if has_score else "no_score"
    if not fr.ok:
        return kind, "blank"
    if has_score and fr.pair == (int(want[0]), int(want[1])):
        return kind, "correct"
    return kind, "wrong"


def field_outcomes(row: dict[str, Any], fr: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not fr.ok:
        return out
    clock = row.get("clock")
    if clock not in (None, "?"):
        out["clock"] = "correct" if fr.clock_text == clock else "wrong"
    q = QUARTER_WORDS.get(str(row.get("quarter") or "").lower())
    if q is not None:
        out["quarter"] = "correct" if fr.quarter == q else "wrong"
    return out


def run_frames(
    rows: list[dict[str, Any]], frames: Path, profile_id: str, loco: bool, pack_path: str | None
) -> dict[str, Any]:
    profile = PROFILES[profile_id]
    full = TemplatePack.load(pack_path) if pack_path else TemplatePack.load(profile.pack_path)
    readers: dict[str, ScorebugReader] = {}
    per_clip: dict[str, Counter[str]] = defaultdict(Counter)
    per_set: dict[str, Counter[str]] = defaultdict(Counter)
    reasons: Counter[str] = Counter()
    wrong: list[dict[str, Any]] = []
    lat: list[float] = []
    for row in rows:
        img = cv2.imread(str(frames / row["frame"]))
        if img is None:
            per_set["_missing"]["frames"] += 1
            continue
        clip = str(row.get("clip"))
        if loco and row.get("skin") == profile.skin_label:
            if clip not in readers:
                pack, _ = build_pack(rows, frames, profile, exclude_clips={clip})
                readers[clip] = ScorebugReader(profile, pack)
            rd = readers[clip]
        else:
            rd = readers.setdefault("_full", ScorebugReader(profile, full))
        t0 = time.perf_counter()
        fr = rd.read(img)
        lat.append(time.perf_counter() - t0)
        kind, outcome = score_frame(row, fr)
        reasons[fr.reason] += 1
        for c in (per_clip[clip], per_set[clip_set(row)]):
            c[f"{kind}_{outcome}"] += 1
            for f, o in field_outcomes(row, fr).items():
                c[f"{f}_{o}"] += 1
        if outcome == "wrong" or "wrong" in field_outcomes(row, fr).values():
            wrong.append(
                {
                    "frame": row["frame"],
                    "want": [
                        row.get("left"),
                        row.get("right"),
                        row.get("quarter"),
                        row.get("clock"),
                    ],
                    "got": [fr.left_score, fr.right_score, fr.quarter, fr.clock_text],
                }
            )
    return {
        "per_clip": {k: dict(v) for k, v in sorted(per_clip.items())},
        "per_set": {k: dict(v) for k, v in sorted(per_set.items())},
        "reasons": dict(reasons.most_common()),
        "wrong": wrong,
        "median_ms": round(1000 * float(np.median(lat)), 3) if lat else None,
    }


def _eight_variants(glyph: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Turn a real '0' glyph into 8-like shapes by inking rows of its hole."""
    ink = dark_on_light_ink(glyph) > 0
    if not ink.any():
        return []
    colour = np.median(glyph[ink], axis=0).astype(np.uint8)
    h = glyph.shape[0]
    mid = h // 2
    out = []
    for name, rows in (("bar", [mid]), ("bar_low", [mid, mid + 1]), ("bar_high", [mid - 1, mid])):
        g = glyph.copy()
        for r in rows:
            if 0 <= r < h:
                g[r][~ink[r]] = colour
        out.append((name, g))
    return out


def run_eight_probe(
    rows: list[dict[str, Any]], frames: Path, profile_id: str, pack_path: str | None
) -> dict[str, Any]:
    """Synthetic-8 probe: every real '0' score glyph closed into an 8-like shape.

    No Madden 8 exists in the box clips, so this is not a template and not a
    substitute for real footage; it checks the reader blanks on that shape.
    Any read that still answers counts as wrong.
    """
    profile = PROFILES[profile_id]
    rd = ScorebugReader(
        profile, TemplatePack.load(pack_path) if pack_path else TemplatePack.load(profile.pack_path)
    )
    c: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    top = rd._band_top()
    for row in rows:
        if row.get("skin") != profile.skin_label or row.get("left") is None:
            continue
        img = cv2.imread(str(frames / row["frame"]))
        if img is None:
            continue
        band, _ = rd.reference_band(img)
        if band is None or rd.check_layout(band)[0] != "ok":
            continue
        _, (dx, dy), _ = rd.check_layout(band)
        for box, val in ((profile.left_score, row["left"]), (profile.right_score, row["right"])):
            if "0" not in str(val):
                continue
            x1, x2, y1, y2 = _shift(box, dx, dy)
            glyphs, why, boxes = rd.score_glyphs(band[y1 - top : y2 - top, x1:x2])
            if glyphs is None or len(boxes) != len(str(val)):
                continue
            for (gx, gy, gw, gh), ch in zip(boxes, str(val), strict=True):
                if ch != "0":
                    continue
                ys, xs = y1 - top + gy, x1 + gx
                for _name, g in _eight_variants(band[ys : ys + gh, xs : xs + gw]):
                    b2 = band.copy()
                    b2[ys : ys + gh, xs : xs + gw] = g
                    fr = rd.read(cv2.resize(_unband(b2, rd), (img.shape[1], img.shape[0])))
                    reasons[fr.reason] += 1
                    c["blank" if not fr.ok else "wrong"] += 1
    return {"counts": dict(c), "reasons": dict(reasons.most_common())}


def _unband(band: np.ndarray, rd: ScorebugReader) -> np.ndarray:
    p = rd.profile
    frame = np.full((p.ref_h, p.ref_w, 3), 60, np.uint8)
    frame[rd._band_top() :] = band
    return frame


def _frame_index(name: str) -> int | None:
    m = re.search(r"_(\d{3})\.(?:jpg|png)$", name)
    return int(m.group(1)) if m else None


def clip_truth(rows: list[dict[str, Any]]) -> dict[str, list[tuple[float, tuple[int, int] | None]]]:
    by: dict[str, list[tuple[float, tuple[int, int] | None]]] = defaultdict(list)
    for r in rows:
        i = _frame_index(r["frame"])
        if i is None or not str(r.get("clip", "")).startswith("hdmi_clip_"):
            continue
        pair = (
            (int(r["left"]), int(r["right"]))
            if r.get("left") is not None and r.get("right") is not None
            else None
        )
        by[r["clip"]].append((i + FRAME_TIME_OFFSET_S, pair))
    return {k: sorted(v) for k, v in by.items()}


def truth_at(
    seq: list[tuple[float, tuple[int, int] | None]], t: float
) -> tuple[bool, tuple[int, int] | None, set[tuple[int, int] | None]]:
    """(scored, pair, neighbours). Scored only when both neighbouring labels agree.

    Unscored frames sit between two labels that differ (a score change, a
    banner); ``neighbours`` holds both labels so a lock there can still be
    checked against them.
    """
    before = [s for s in seq if s[0] <= t]
    after = [s for s in seq if s[0] >= t]
    if not before or not after:
        near = before[-1] if before else after[0]
        return (abs(near[0] - t) <= 0.5, near[1], {near[1]})
    a, b = before[-1], after[0]
    if a[1] == b[1]:
        return True, a[1], {a[1]}
    return False, None, {a[1], b[1]}


def run_clips(
    rows: list[dict[str, Any]],
    clip_dirs: list[Path],
    profile_id: str,
    pack_path: str | None,
    loco: bool,
    frames: Path,
) -> dict[str, Any]:
    profile = PROFILES[profile_id]
    truth = clip_truth(rows)
    skin_of = {}
    for r in rows:
        skin_of.setdefault(r.get("clip"), Counter())[r.get("skin")] += 1
    full = TemplatePack.load(pack_path) if pack_path else TemplatePack.load(profile.pack_path)
    out: dict[str, Any] = {}
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    for clip, seq in sorted(truth.items()):
        path = next((d / f"{clip}.mp4" for d in clip_dirs if (d / f"{clip}.mp4").is_file()), None)
        if path is None:
            continue
        pack = full
        if loco and skin_of[clip].get(profile.skin_label):
            pack, _ = build_pack(rows, frames, profile, exclude_clips={clip})
        svc = LocalScorebugService(ScorebugReader(profile, pack), AgreementConfig())
        cap = cv2.VideoCapture(str(path))
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        c: Counter[str] = Counter()
        n = 0
        while True:
            ok, img = cap.read()
            if not ok:
                break
            t = n / fps
            n += 1
            board = svc.observe(
                img,
                stamp={"seq": n, "clock_ns": int(t * 1e9)},
                session_id=clip,
                game_state="gameplay",
                now_ns=int(t * 1e9),
            )
            scored, pair, neighbours = truth_at(seq, t)
            if not scored:
                c["unscored"] += 1
                # A lock between two different labels must equal one of them.
                if board is not None and (board["left_score"], board["right_score"]) not in neighbours:
                    c["transition_wrong"] += 1
                continue
            kind = "score" if pair is not None else "no_score"
            if board is None:
                c[f"{kind}_blank"] += 1
            elif pair is not None and (board["left_score"], board["right_score"]) == pair:
                c[f"{kind}_correct"] += 1
            else:
                c[f"{kind}_wrong"] += 1
        cap.release()
        # A clip counts toward a skin's set if any labelled frame shows that
        # skin (Madden clips often open on a no-scorebug intro).
        skins = skin_of[clip]
        dominant = next(
            (k for k in (profile.skin_label, "madden_dark", "cfb") if skins.get(k)),
            skins.most_common(1)[0][0],
        )
        out[clip] = {"frames": n, "fps": round(fps, 2), "skin": dominant, **dict(c)}
        for k, v in c.items():
            totals[dominant][k] += v
    return {"per_clip": out, "per_set": {k: dict(v) for k, v in totals.items()}}


def _line(name: str, c: dict[str, int]) -> str:
    s = f"{name:34s} score: correct {c.get('score_correct', 0):4d}  blank {c.get('score_blank', 0):4d}  wrong {c.get('score_wrong', 0):3d}"
    s += (
        f" | no-score: blank {c.get('no_score_blank', 0):4d}  wrong {c.get('no_score_wrong', 0):3d}"
    )
    if "clock_correct" in c or "clock_wrong" in c:
        s += f" | clock ok {c.get('clock_correct', 0)} wrong {c.get('clock_wrong', 0)}"
    if "quarter_correct" in c or "quarter_wrong" in c:
        s += f" | qtr ok {c.get('quarter_correct', 0)} wrong {c.get('quarter_wrong', 0)}"
    if "unscored" in c:
        s += f" | transition frames {c['unscored']} (wrong {c.get('transition_wrong', 0)})"
    return s


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Offline eval for the local scorebug reader")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--frames", required=True)
    ap.add_argument(
        "--clips", action="append", default=[], help="folder with <clip>.mp4 (repeatable)"
    )
    ap.add_argument("--profile", default="madden27_standard", choices=sorted(PROFILES))
    ap.add_argument("--pack", default=None, help="template pack (default: shipped pack)")
    ap.add_argument("--loco", action="store_true", help="leave-one-clip-out template packs")
    ap.add_argument("--json", default=None, help="also write full results here")
    ap.add_argument("--eight-probe", action="store_true", help="also run the synthetic-8 probe")
    args = ap.parse_args(argv)
    rows = load_labels(args.labels)["frames"]
    frames = Path(args.frames)
    res: dict[str, Any] = {"mode": "loco" if args.loco else "shipped_pack"}
    res["frames"] = run_frames(rows, frames, args.profile, args.loco, args.pack)
    print(f"== frame mode ({res['mode']}), median {res['frames']['median_ms']} ms/frame ==")
    for k, v in res["frames"]["per_set"].items():
        print(_line(f"[set] {k}", v))
    for k, v in res["frames"]["per_clip"].items():
        print(_line(k, v))
    print("blank reasons:", res["frames"]["reasons"])
    for w in res["frames"]["wrong"]:
        print("  WRONG", w)
    wrong = sum(
        v.get("score_wrong", 0)
        + v.get("no_score_wrong", 0)
        + v.get("clock_wrong", 0)
        + v.get("quarter_wrong", 0)
        for v in res["frames"]["per_set"].values()
    )
    if args.eight_probe:
        res["eight_probe"] = run_eight_probe(rows, frames, args.profile, args.pack)
        ep = res["eight_probe"]
        print(
            f"== synthetic-8 probe (real '0' glyphs inked into 8 shapes): {ep['counts']} reasons {ep['reasons']}"
        )
        wrong += ep["counts"].get("wrong", 0)
    if args.clips:
        res["clips"] = run_clips(
            rows, [Path(d) for d in args.clips], args.profile, args.pack, args.loco, frames
        )
        print(f"== clip mode ({res['mode']}): every decoded frame through the agreement window ==")
        for k, v in res["clips"]["per_set"].items():
            print(_line(f"[set] {k}", v))
        for k, v in res["clips"]["per_clip"].items():
            print(_line(f"{k} ({v['skin']}, {v['frames']}f@{v['fps']})", v))
        wrong += sum(
            v.get("score_wrong", 0) + v.get("no_score_wrong", 0)
            for v in res["clips"]["per_set"].values()
        )
    if args.json:
        Path(args.json).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
    print(f"TOTAL WRONG = {wrong}")
    return 1 if wrong else 0


if __name__ == "__main__":
    raise SystemExit(main())
