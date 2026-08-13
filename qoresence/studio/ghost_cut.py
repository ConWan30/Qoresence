"""Local Ghost Cut — cinematic highlight from the real HDMI clip.

No LTX. No cloud. OpenCV only. Burns Qoresence chapter / score / button
evidence onto the operator's own footage.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .receipt import ReelReceipt, now_ns, write_receipt

log = logging.getLogger(__name__)


@dataclass
class GhostCutResult:
    output_path: Path
    receipt_path: Path
    frames: int
    duration_s: float


def _score_line(situation: dict[str, Any] | None) -> str:
    if not situation:
        return ""
    home = situation.get("home_score")
    away = situation.get("away_score")
    if home is None and away is None:
        return ""
    q = situation.get("quarter")
    qpart = f"  Q{q}" if q not in (None, "") else ""
    return f"{home or 0}-{away or 0}{qpart}"


def _active_buttons(buttons_summary: dict[str, Any] | None) -> list[str]:
    if not buttons_summary:
        return []
    if isinstance(buttons_summary.get("pressed"), list):
        return [str(x) for x in buttons_summary["pressed"][:6]]
    names: list[str] = []
    for key, val in buttons_summary.items():
        if key in {"duration_s", "events"}:
            continue
        try:
            if float(val) > 0:
                names.append(str(key))
        except (TypeError, ValueError):
            continue
    return names[:6]


def _draw_hud(
    bgr: np.ndarray,
    *,
    kind: str,
    label: str,
    score: str,
    buttons: list[str],
    t_s: float,
    duration_s: float,
) -> np.ndarray:
    frame = bgr.copy()
    h, w = frame.shape[:2]
    glass = frame.copy()
    cv2.rectangle(glass, (0, 0), (w, 36), (12, 16, 10), -1)
    cv2.rectangle(glass, (0, h - 86), (w, h), (10, 12, 8), -1)
    frame = cv2.addWeighted(glass, 0.62, frame, 0.38, 0)
    cv2.line(frame, (0, 36), (w, 36), (106, 242, 200), 1, cv2.LINE_AA)
    cv2.line(frame, (0, h - 86), (w, h - 86), (106, 242, 200), 1, cv2.LINE_AA)

    tick_w = max(8, int(w * min(1.0, t_s / max(duration_s, 0.01))))
    cv2.rectangle(frame, (0, h - 4), (tick_w, h), (106, 242, 200), -1)

    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(frame, "QORESENCE  GHOST CUT", (18, 24), font, 0.48, (200, 242, 106), 1, cv2.LINE_AA)
    cv2.putText(frame, f"{t_s:05.2f}s", (w - 118, 24), font, 0.48, (145, 161, 173), 1, cv2.LINE_AA)

    kind_s = (kind or "chapter").upper()[:18]
    cv2.putText(frame, kind_s, (18, h - 52), font, 0.62, (104, 217, 232), 1, cv2.LINE_AA)
    if score:
        cv2.putText(frame, score, (18, h - 24), font, 0.72, (238, 245, 244), 2, cv2.LINE_AA)
    lab = (label or "")[:64]
    if lab:
        cv2.putText(frame, lab, (200, h - 24), font, 0.48, (145, 161, 173), 1, cv2.LINE_AA)
    if buttons:
        chips = "  ".join(b.upper() for b in buttons)
        cv2.putText(frame, chips, (w - 18 - 11 * len(chips), h - 52), font, 0.45, (246, 189, 98), 1, cv2.LINE_AA)
    return frame


def cut_highlight(
    clip_path: str | Path,
    chapter: dict[str, Any],
    *,
    situation: dict[str, Any] | None = None,
    buttons_summary: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
    session_id: str = "",
    game_profile: str = "",
    pre_s: float = 2.0,
    post_s: float = 4.0,
    slow_last_s: float = 1.2,
    slow_factor: float = 0.5,
) -> GhostCutResult:
    """Cut a local highlight around chapter t_s and burn the causal HUD."""
    clip_path = Path(clip_path)
    if not clip_path.is_file():
        raise FileNotFoundError(clip_path)

    t_s = float(chapter.get("t_s") or 0.0)
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open clip: {clip_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    clip_dur = total / fps if fps > 0 else 0.0

    start_s = max(0.0, t_s - pre_s)
    end_s = min(clip_dur, t_s + post_s) if clip_dur else t_s + post_s
    if end_s <= start_s:
        end_s = start_s + 1.0
    start_f = int(start_s * fps)
    end_f = max(start_f + 1, int(end_s * fps))
    slow_from = max(start_s, end_s - slow_last_s)

    if output_path is None:
        out_dir = clip_path.parent / (clip_path.stem + "_cut")
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"reel_ghost_{int(t_s * 1000):06d}.mp4"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"cannot write {output_path}")

    kind = str(chapter.get("kind") or "chapter")
    label = str(chapter.get("label") or "")
    score = _score_line(situation)
    buttons = _active_buttons(buttons_summary)
    written = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    for idx in range(start_f, min(end_f, total if total else end_f)):
        ok, bgr = cap.read()
        if not ok or bgr is None:
            break
        if bgr.shape[1] != width or bgr.shape[0] != height:
            bgr = cv2.resize(bgr, (width, height))
        rel = (idx / fps) - start_s
        hud = _draw_hud(
            bgr,
            kind=kind,
            label=label,
            score=score,
            buttons=buttons,
            t_s=rel,
            duration_s=end_s - start_s,
        )
        repeats = 1
        abs_t = idx / fps
        if abs_t >= slow_from and slow_factor > 0:
            repeats = max(1, int(round(1.0 / slow_factor)))
        for _ in range(repeats):
            writer.write(hud)
            written += 1
    cap.release()
    writer.release()
    if written <= 0:
        raise RuntimeError("Ghost Cut wrote no frames")

    duration_out = written / fps if fps else 0.0
    receipt = ReelReceipt(
        session_id=session_id,
        source_clip=str(clip_path),
        source_t_s=t_s,
        ltx_job_id="",
        ltx_prompt="ghost_cut",
        ltx_payload_hash="ghost",
        output_path=str(output_path),
        created_ns=now_ns(),
        completed_ns=now_ns(),
        status="completed",
        game_profile=game_profile,
        chapter_kind=kind,
        chapter_label=label,
        metadata={
            "renderer": "ghost_cut",
            "pre_s": pre_s,
            "post_s": post_s,
            "slow_last_s": slow_last_s,
            "frames": written,
            "duration_s": round(duration_out, 3),
            "score": score,
            "buttons": buttons,
        },
    )
    receipt_path = write_receipt(output_path, receipt)
    log.info("Ghost Cut: %s -> %s (%d frames)", clip_path.name, output_path.name, written)
    return GhostCutResult(
        output_path=output_path,
        receipt_path=receipt_path,
        frames=written,
        duration_s=duration_out,
    )


def buttons_from_sidecar(clip_path: str | Path) -> dict[str, Any]:
    """Best-effort pressed-name summary from a *.buttons.json sidecar."""
    p = Path(clip_path).with_name(Path(clip_path).stem + ".buttons.json")
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data.get("buttons_summary"), dict):
        return data["buttons_summary"]
    names: dict[str, int] = {}
    for ev in data.get("events") or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("kind") != "press":
            continue
        name = str(ev.get("name") or "")
        if name:
            names[name] = names.get(name, 0) + 1
    return names
