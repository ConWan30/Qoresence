"""Clip-excision pilot gate — score Cut Receipts against a hand-labelled clip set.

Read-only over clips, receipts, labels and saved ``/health`` snapshots. It never
flips a default: a ``pass`` is evidence for a human to review, not a switch.

Labels file (JSON, source-clip seconds)::

    {"clips": {"hdmi_clip_20260925_010203.mp4": {
        "profile": "madden_27",
        "dead": [[4.2, 11.8, "pause"], [20.0, 26.5, "loading"]]}}}

Every second not inside a ``dead`` span is treated as live play. Over-cut is any
policy cut that removes live play; the gate requires it to be exactly zero.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from qoresence.vision import clip_excise as cx

GATE_MIN_CLIPS = 20
GATE_KINDS = ("pause", "menu", "loading")
AGE_S_MAX = 1.0
EDGE_TOL_S = 0.1
LABEL_SCHEMA = "qoresence.excise_labels/1"
REPORT_SCHEMA = "qoresence.excise_gate/1"


def load_labels(path: Any) -> dict[str, dict[str, Any]]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    clips = raw.get("clips") if isinstance(raw, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for name, entry in (clips or {}).items():
        dead = []
        for d in (entry or {}).get("dead") or []:
            if isinstance(d, (list, tuple)) and len(d) >= 2:
                t0, t1 = float(d[0]), float(d[1])
                if t1 > t0:
                    kind = str(d[2]) if len(d) >= 3 and d[2] else "dead"
                    dead.append([t0, t1, kind])
        out[str(name)] = {"profile": (entry or {}).get("profile"), "dead": dead}
    return out


def system_cuts(receipt: dict[str, Any]) -> list[list[float]]:
    """Cuts the policy alone would make (gamer overrides stripped)."""
    rows = [dict(r, user=None) for r in receipt.get("spans") or []]
    cuts, _keep, _aborted = cx.plan_cuts(rows, float(receipt.get("source_duration_s") or 0))
    return cuts


def _uncovered(ranges: list[list[float]], cover: list[list[float]], tol: float) -> float:
    """Seconds of ``ranges`` not covered by ``cover`` (cover widened by ``tol``)."""
    widened = sorted([float(c[0]) - tol, float(c[1]) + tol] for c in cover)
    total = 0.0
    for r0, r1 in ranges:
        covered = 0.0
        for c0, c1 in widened:
            covered += max(0.0, min(r1, c1) - max(r0, c0))
        total += max(0.0, (r1 - r0) - covered)
    return round(total, 3)


def witness_ranges(receipt: dict[str, Any]) -> list[list[float]]:
    """Proposed seconds from witness spans. Suggestions are not cuts."""

    out: list[list[float]] = []
    for row in receipt.get("spans") or []:
        if not str(row.get("reason") or "").startswith("witness:"):
            continue
        try:
            t0, t1 = float(row["t0_s"]), float(row["t1_s"])
        except (TypeError, ValueError, KeyError):
            continue
        if t1 > t0:
            out.append([t0, t1])
    return out


def score_clip(
    receipt: dict[str, Any], label: dict[str, Any], *, tol: float = EDGE_TOL_S
) -> dict[str, Any]:
    cuts = system_cuts(receipt)
    dead = [[d[0], d[1]] for d in label.get("dead") or []]
    dead_s = round(sum(d[1] - d[0] for d in dead), 3)
    cut_s = round(sum(c[1] - c[0] for c in cuts), 3)
    proposed = witness_ranges(receipt)
    proposed_s = round(sum(p[1] - p[0] for p in proposed), 3)
    rows = receipt.get("spans") or []
    return {
        "clip": receipt.get("source"),
        "profile": label.get("profile") or receipt.get("game_profile"),
        "referee": receipt.get("referee"),
        "model": receipt.get("model"),
        "policy_version": receipt.get("policy_version"),
        "excision": receipt.get("excision"),
        "dead_kinds": sorted({d[2] for d in label.get("dead") or []}),
        "dead_s": dead_s,
        "cut_s": cut_s,
        "over_cut_s": _uncovered(cuts, dead, tol),
        "under_cut_s": _uncovered(dead, cuts, 0.0),
        "health_age_s_max": (receipt.get("health") or {}).get("age_s_max"),
        "health_samples": int((receipt.get("health") or {}).get("samples") or 0),
        "spans_cut": sum(1 for r in rows if r.get("decision") == "cut"),
        "spans_suggest": sum(1 for r in rows if r.get("decision") == "suggest"),
        "witness_proposed_s": proposed_s,
        "witness_over_s": _uncovered(proposed, dead, tol),
        "witness_under_s": _uncovered(dead, proposed, 0.0),
    }


def label_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Deck clicks: suggestion accept rate, vetoes of auto-cuts, rescues of keeps.

    Only the latest click per (source, span) counts.
    """
    latest: dict[tuple[Any, Any], dict[str, Any]] = {}
    for r in rows:
        latest[(r.get("source"), r.get("span_id"))] = r
    final = list(latest.values())
    suggested = [r for r in final if r.get("system") == "suggest"]
    accepted = sum(1 for r in suggested if r.get("user") == "cut")
    return {
        "clicks": len(rows),
        "spans_decided": len(final),
        "suggestions_decided": len(suggested),
        "suggestions_accepted": accepted,
        "suggest_accept_rate": round(accepted / len(suggested), 3) if suggested else None,
        "vetoes": [
            {"source": r.get("source"), "span_id": r.get("span_id"), "reason": r.get("reason")}
            for r in final
            if r.get("system") == "cut" and r.get("user") == "keep"
        ],
        "rescues": sum(1 for r in final if r.get("system") == "keep" and r.get("user") == "cut"),
    }


def _age_from(doc: Any) -> float | None:
    if not isinstance(doc, dict):
        return None
    for root in (doc.get("health"), doc):
        if not isinstance(root, dict):
            continue
        state = root.get("state") if isinstance(root.get("state"), dict) else root
        video = state.get("video") if isinstance(state, dict) else None
        if isinstance(video, dict) and video.get("age_s") is not None:
            try:
                return float(video["age_s"])
            except (TypeError, ValueError):
                return None
    return None


def health_ages(paths: list[Any]) -> list[float]:
    """``state.video.age_s`` from saved ``/health`` or pilot_snapshot JSON / JSONL."""
    ages: list[float] = []
    for p in paths:
        try:
            text = Path(p).read_text(encoding="utf-8")
        except OSError:
            continue
        docs: list[Any] = []
        try:
            docs = [json.loads(text)]
        except json.JSONDecodeError:
            for line in text.splitlines():
                try:
                    docs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for d in docs:
            age = _age_from(d)
            if age is not None:
                ages.append(age)
    return ages


def evaluate(
    clips_dir: Any,
    labels: dict[str, dict[str, Any]],
    *,
    health_files: list[Any] | None = None,
    pinned_model: str | None = None,
    min_clips: int = GATE_MIN_CLIPS,
) -> dict[str, Any]:
    clips_dir = Path(clips_dir)
    pinned = pinned_model or cx.excise_model()
    scored: list[dict[str, Any]] = []
    missing: list[str] = []
    for name, label in sorted(labels.items()):
        receipt = cx.read_receipt(clips_dir / name)
        if receipt is None:
            missing.append(name)
            continue
        scored.append(score_clip(receipt, label))

    football = [s for s in scored if cx.is_football_profile(s["profile"])]
    with_dead = [s for s in football if s["dead_s"] > 0]
    kinds_seen = sorted({k for s in with_dead for k in s["dead_kinds"]})
    models = sorted({s["model"] for s in scored if s["referee"] == "jev" and s["model"]})
    clicks = label_stats(cx.read_labels(clips_dir / cx.LABELS_FILE))
    file_ages = health_ages(health_files or [])
    receipt_ages = [
        float(s["health_age_s_max"]) for s in scored if s["health_age_s_max"] is not None
    ]
    ages = file_ages + receipt_ages
    over = [s for s in scored if s["over_cut_s"] > 0]

    failures: list[str] = []
    if over:
        failures.append(f"over_cut on {len(over)} clip(s)")
    if clicks["vetoes"]:
        failures.append(f"gamer vetoed {len(clicks['vetoes'])} auto-cut(s)")
    if ages and max(ages) >= AGE_S_MAX:
        failures.append(f"age_s peaked at {max(ages):.2f}s (limit {AGE_S_MAX:.1f}s)")
    if [m for m in models if m != pinned]:
        failures.append(f"receipts from unpinned model(s) {models}; pin is {pinned}")

    gaps: list[str] = []
    if len(with_dead) < min_clips:
        gaps.append(f"{len(with_dead)}/{min_clips} football clips with labelled dead spans")
    missing_kinds = [k for k in GATE_KINDS if k not in kinds_seen]
    if missing_kinds:
        gaps.append("no labelled " + ", ".join(missing_kinds))
    if missing:
        gaps.append(f"{len(missing)} labelled clip(s) have no receipt")
    if not ages:
        gaps.append("no /health samples captured during excision")

    verdict = "fail" if failures else ("insufficient" if gaps else "pass")
    total_dead = sum(s["dead_s"] for s in scored)
    total_under = sum(s["under_cut_s"] for s in scored)
    return {
        "schema": REPORT_SCHEMA,
        "policy_version": cx.POLICY_VERSION,
        "pinned_model": pinned,
        "verdict": verdict,
        "failures": failures,
        "gaps": gaps,
        "summary": {
            "clips_labelled": len(labels),
            "clips_scored": len(scored),
            "football_clips_with_dead": len(with_dead),
            "dead_kinds_seen": kinds_seen,
            "over_cut_s": round(sum(s["over_cut_s"] for s in scored), 3),
            "under_cut_s": round(total_under, 3),
            "dead_removed_fraction": round(1 - total_under / total_dead, 3) if total_dead else None,
            "models": models,
            "age_s_max": round(max(ages), 3) if ages else None,
            "age_s_samples": len(ages),
            "age_s_from_files": len(file_ages),
            "age_s_from_receipts": len(receipt_ages),
            "witness_proposed_s": round(sum(s["witness_proposed_s"] for s in scored), 3),
            "witness_dead_s": round(sum(s["dead_s"] for s in scored), 3),
            "witness_over_s": round(sum(s["witness_over_s"] for s in scored), 3),
            "witness_under_s": round(sum(s["witness_under_s"] for s in scored), 3),
        },
        "clicks": clicks,
        "clips": scored,
        "missing_receipts": missing,
        "licenses_digits": False,
        "note": "Evidence for human review only; this report never changes a default.",
    }


GROUND_TRUTH_FILE = "excise_ground_truth.json"
MAX_DEAD_PER_CLIP = 50
_gt_lock = threading.Lock()  # file write only; no bus, no lobe lock


def ground_truth_path(clips_dir: Any) -> Path:
    return Path(clips_dir) / GROUND_TRUTH_FILE


def _read_ground_truth(clips_dir: Any) -> dict[str, Any]:
    try:
        doc = json.loads(ground_truth_path(clips_dir).read_text(encoding="utf-8"))
        if isinstance(doc, dict) and isinstance(doc.get("clips"), dict):
            return doc
    except Exception:
        pass
    return {"schema": LABEL_SCHEMA, "clips": {}}


def clean_dead(dead: Any, *, duration_s: float | None = None) -> list[list[Any]] | None:
    """Validate Deck-marked dead spans. ``None`` when the input is malformed."""
    if not isinstance(dead, list) or len(dead) > MAX_DEAD_PER_CLIP:
        return None
    out: list[list[Any]] = []
    for d in dead:
        if not isinstance(d, (list, tuple)) or len(d) != 3 or d[2] not in GATE_KINDS:
            return None
        try:
            t0, t1 = round(float(d[0]), 3), round(float(d[1]), 3)
        except (TypeError, ValueError):
            return None
        if duration_s:
            t1 = min(t1, round(float(duration_s), 3))
        if t0 < 0 or t1 <= t0:
            return None
        out.append([t0, t1, str(d[2])])
    return sorted(out)


def clip_labels(clips_dir: Any, clip_name: str) -> dict[str, Any] | None:
    return _read_ground_truth(clips_dir)["clips"].get(clip_name)


def set_clip_labels(
    clips_dir: Any, clip_name: str, dead: list[list[Any]], *, profile: str | None
) -> dict[str, Any]:
    """Store one clip's hand labels (atomic rewrite of the ground-truth file)."""
    entry = {"profile": profile, "dead": dead, "labelled_at": round(time.time(), 3)}
    with _gt_lock:
        doc = _read_ground_truth(clips_dir)
        doc["schema"] = LABEL_SCHEMA
        doc["clips"][clip_name] = entry
        out = ground_truth_path(clips_dir)
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        tmp.replace(out)
    return entry


def gate_status(clips_dir: Any) -> dict[str, Any]:
    """Compact gate view for the Deck; ``age_s`` comes from receipts sampled during excision."""
    labels = (
        load_labels(ground_truth_path(clips_dir)) if ground_truth_path(clips_dir).is_file() else {}
    )
    r = evaluate(clips_dir, labels)
    return {
        "verdict": r["verdict"],
        "failures": r["failures"],
        "gaps": r["gaps"],
        "summary": {
            k: r["summary"][k]
            for k in (
                "clips_labelled",
                "football_clips_with_dead",
                "dead_kinds_seen",
                "over_cut_s",
                "dead_removed_fraction",
                "age_s_max",
            )
        },
        "min_clips": GATE_MIN_CLIPS,
        "suggest_accept_rate": r["clicks"]["suggest_accept_rate"],
        "vetoes": len(r["clicks"]["vetoes"]),
        "licenses_digits": False,
    }


def excise_preflight(clips_dir: Any, *, repo_root: Any = None) -> list[tuple[str, str]]:
    """Soft pilot checks as ``(level, message)``; level is ``ok`` / ``warn`` / ``info``. Never fails."""
    import os
    import shutil

    out: list[tuple[str, str]] = []
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    out.append(
        ("warn", f"{' and '.join(missing)} not on PATH — cut renders will fail")
        if missing
        else ("ok", "ffmpeg + ffprobe on PATH")
    )
    d = Path(clips_dir)
    probe = d if d.exists() else d.parent
    out.append(
        ("ok", f"clips folder writable: {d}")
        if os.access(probe, os.W_OK)
        else ("warn", f"clips folder not writable: {d}")
    )
    profile = cx.current_game_profile()
    if cx.is_football_profile(profile):
        out.append(("ok", f"football profile pinned: {profile} (frozen-clock proof on)"))
    else:
        out.append(
            (
                "warn",
                f"profile {profile or 'unpinned'} — offline cuts need an Options press; "
                "pin with --game-profile madden_27 or ncaa_football_27",
            )
        )
    out.append(
        ("ok", "QORESENCE_CLIP_EXCISE=1 set")
        if cx.excise_enabled()
        else ("info", "start with --clip-excise (default OFF)")
    )
    root = Path(repo_root) if repo_root else Path(".")
    has_key = (
        bool(os.environ.get("TYPESAFE_API_KEY", "").strip())
        or (root / ".secrets" / "typesafe.key").is_file()
    )
    out.append(
        (
            "ok",
            f"TypeSafe key found — add --noul or --jev for the Jev referee ({cx.excise_model()})",
        )
        if has_key
        else ("info", "no TypeSafe key — offline Triple Proof only (pauses)")
    )
    if d.is_dir() and any(d.glob("*.cut.json")):
        st = gate_status(d)
        sm = st["summary"]
        out.append(
            (
                "info",
                f"pilot gate {st['verdict']}: {sm['football_clips_with_dead']}/{GATE_MIN_CLIPS} "
                f"labelled football clips, over-cut {sm['over_cut_s']}s",
            )
        )
    return out


def init_labels(clips_dir: Any) -> dict[str, Any]:
    """Blank labels for every clip that has a receipt; candidates shown for reference only."""
    clips: dict[str, Any] = {}
    for rp in sorted(Path(clips_dir).glob("*.cut.json")):
        mp4 = rp.with_name(rp.name[: -len(".cut.json")] + ".mp4")
        receipt = cx.read_receipt(mp4)
        if receipt is None or not mp4.is_file():
            continue
        clips[mp4.name] = {
            "profile": receipt.get("game_profile"),
            "dead": [],
            "_candidates_do_not_copy": [
                [r.get("t0_s"), r.get("t1_s"), r.get("kinds")] for r in receipt.get("spans") or []
            ],
        }
    return {
        "schema": LABEL_SCHEMA,
        "how": (
            "Watch each ORIGINAL clip and list every pause/menu/loading span as "
            "[t0_s, t1_s, kind]. Label from the picture, not from the candidates."
        ),
        "clips": clips,
    }
