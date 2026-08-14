"""Local Ghost Cut — highlight from the real HDMI clip.

Burns chapter, score, and *timed* controller ghosts onto the operator's
own footage. No cloud, no generative model.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from qoresence.sync.event_bind import HidOnset, VisualOnset, bind_onsets

from .receipt import ReelReceipt, now_ns, write_receipt

log = logging.getLogger(__name__)

def _norm_btn(name: str) -> str:
    n = name.lower().replace("-", "_").strip()
    for suffix in ("_btn", "_button", "_key"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return {"a": "cross", "b": "circle", "x": "square", "y": "triangle"}.get(n, n)


_FACE = {
    "triangle": (0, -1),
    "circle": (1, 0),
    "cross": (0, 1),
    "square": (-1, 0),
}
_SHOULDERS = ("l2", "l1", "r1", "r2")


@dataclass
class GhostEvent:
    t_s: float
    name: str
    kind: str
    value: float = 0.0
    imu_precursor_ms: float | None = None


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


def load_button_timeline(clip_path: str | Path) -> list[GhostEvent]:
    """Map *.buttons.json events onto clip-relative seconds."""
    p = Path(clip_path).with_name(Path(clip_path).stem + ".buttons.json")
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = data.get("events") or []
    clocks = [int(e.get("clock_ns") or 0) for e in raw if isinstance(e, dict)]
    clocks = [c for c in clocks if c > 0]
    t0 = min(clocks) if clocks else 0
    out: list[GhostEvent] = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        name = _norm_btn(str(ev.get("name") or ""))
        if not name:
            continue
        cns = int(ev.get("clock_ns") or 0)
        if ev.get("t_s") is not None:
            t = float(ev["t_s"])
        elif cns and t0:
            t = (cns - t0) / 1e9
        else:
            continue
        try:
            val = float(ev.get("value") or 0.0)
        except (TypeError, ValueError):
            val = 0.0
        prec = ev.get("imu_precursor_ms")
        try:
            prec_f = float(prec) if prec is not None else None
        except (TypeError, ValueError):
            prec_f = None
        out.append(
            GhostEvent(
                t_s=t,
                name=name,
                kind=str(ev.get("kind") or "press"),
                value=val,
                imu_precursor_ms=prec_f,
            )
        )
    out.sort(key=lambda e: e.t_s)
    return out


def held_at(timeline: list[GhostEvent], t_s: float) -> set[str]:
    """Buttons down at t_s, plus presses in the last 180ms (flash)."""
    held: set[str] = set()
    flash: set[str] = set()
    for ev in timeline:
        if ev.t_s > t_s + 0.01:
            break
        if ev.kind == "press":
            held.add(ev.name)
            if t_s - ev.t_s <= 0.18:
                flash.add(ev.name)
        elif ev.kind == "release":
            held.discard(ev.name)
        elif ev.kind == "trigger":
            if ev.value > 0.15:
                held.add(ev.name)
            else:
                held.discard(ev.name)
    return held | flash


def precursor_at(timeline: list[GhostEvent], t_s: float) -> list[tuple[str, float]]:
    """Buttons whose IMU jolt is live: ``t`` in [press − precursor_ms, press)."""
    pending: list[tuple[str, float, float]] = []
    for ev in timeline:
        if ev.kind == "press":
            pass
        elif ev.kind == "trigger" and ev.value > 0.15:
            pass
        else:
            continue
        prec = ev.imu_precursor_ms
        if prec is None or prec <= 0:
            continue
        t_jolt = ev.t_s - (prec / 1000.0)
        if t_jolt <= t_s < ev.t_s:
            pending.append((ev.name, prec, ev.t_s))
    pending.sort(key=lambda row: row[2])
    return [(name, prec) for name, prec, _ in pending]


def _binds_for_cut(timeline: list[GhostEvent], chapter: dict[str, Any]) -> list[dict[str, Any]]:
    """Clip-relative TEMPORAL binds (HID before chapter mark). Observation only."""
    try:
        t_mark = float(chapter.get("t_s") or 0.0)
    except (TypeError, ValueError):
        t_mark = 0.0
    visuals = [
        VisualOnset(
            clock_ns=int(t_mark * 1e9),
            kind=str(chapter.get("kind") or "chapter"),
            label=str(chapter.get("label") or ""),
        )
    ]
    hids: list[HidOnset] = []
    for ev in timeline:
        if ev.kind not in {"press", "trigger"}:
            continue
        if ev.kind == "trigger" and ev.value <= 0.15:
            continue
        hids.append(
            HidOnset(
                clock_ns=int(ev.t_s * 1e9),
                name=ev.name,
                kind=ev.kind,
                imu_precursor_ms=ev.imu_precursor_ms,
            )
        )
    return [b.to_dict() for b in bind_onsets(visuals, hids)]


def buttons_from_sidecar(clip_path: str | Path) -> dict[str, Any]:
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
        if isinstance(ev, dict) and ev.get("kind") == "press" and ev.get("name"):
            n = str(ev["name"])
            names[n] = names.get(n, 0) + 1
    return names


def _draw_ps_face(frame: np.ndarray, name: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    """PlayStation face glyphs. Hershey cannot draw △□○✕ reliably."""
    if name == "triangle":
        pts = np.array([[x, y - 5], [x - 5, y + 4], [x + 5, y + 4]], np.int32)
        cv2.polylines(frame, [pts], True, color, 1, cv2.LINE_AA)
    elif name == "square":
        cv2.rectangle(frame, (x - 4, y - 4), (x + 4, y + 4), color, 1, cv2.LINE_AA)
    elif name == "circle":
        cv2.circle(frame, (x, y), 5, color, 1, cv2.LINE_AA)
    elif name == "cross":
        cv2.line(frame, (x - 4, y - 4), (x + 4, y + 4), color, 1, cv2.LINE_AA)
        cv2.line(frame, (x + 4, y - 4), (x - 4, y + 4), color, 1, cv2.LINE_AA)


def _draw_pad(
    frame: np.ndarray,
    held: set[str],
    origin: tuple[int, int],
    body: set[str] | None = None,
) -> None:
    """DualSense-ish ghost. Held = phosphor; IMU precursor = cyan body."""
    ox, oy = origin
    font = cv2.FONT_HERSHEY_SIMPLEX
    on = (106, 242, 200)
    body_col = (232, 217, 104)
    off = (70, 82, 76)
    body = body or set()

    def _color(name: str) -> tuple[int, int, int]:
        if name in held:
            return on
        if name in body:
            return body_col
        return off

    # shoulders
    labels = [("l2", 0), ("l1", 1), ("r1", 3), ("r2", 4)]
    for name, col in labels:
        x = ox + col * 36
        color = _color(name)
        cv2.rectangle(frame, (x, oy), (x + 32, oy + 16), color, 1, cv2.LINE_AA)
        cv2.putText(frame, name.upper(), (x + 3, oy + 12), font, 0.32, color, 1, cv2.LINE_AA)
    # face cluster — DualSense △ ○ ✕ □ (not Xbox Y/B/A/X)
    cx, cy = ox + 90, oy + 58
    for name, (dx, dy) in _FACE.items():
        x = int(cx + dx * 28)
        y = int(cy + dy * 22)
        color = _color(name)
        cv2.circle(frame, (x, y), 11, color, 1, cv2.LINE_AA)
        _draw_ps_face(frame, name, x, y, color)
    extras = [n for n in sorted(held | body) if n not in _FACE and n not in _SHOULDERS]
    if extras:
        cv2.putText(frame, " ".join(extras[:4]).upper(), (ox, oy + 96), font, 0.36, on, 1, cv2.LINE_AA)


def _draw_hud(
    bgr: np.ndarray,
    *,
    kind: str,
    label: str,
    score: str,
    held: set[str],
    t_s: float,
    duration_s: float,
    body: set[str] | None = None,
    body_line: str = "",
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
    cv2.putText(frame, (kind or "chapter").upper()[:18], (18, h - 52), font, 0.62, (104, 217, 232), 1, cv2.LINE_AA)
    if score:
        cv2.putText(frame, score, (18, h - 24), font, 0.72, (238, 245, 244), 2, cv2.LINE_AA)
    lab = (label or "")[:56]
    if lab:
        cv2.putText(frame, lab, (200, h - 24), font, 0.48, (145, 161, 173), 1, cv2.LINE_AA)
    if body_line:
        cv2.putText(frame, body_line, (w - 210, h - 52), font, 0.42, (232, 217, 104), 1, cv2.LINE_AA)
    _draw_pad(frame, held, (w - 210, h - 168), body=body)
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
    timeline: list[GhostEvent] | None = None,
) -> GhostCutResult:
    clip_path = Path(clip_path)
    if not clip_path.is_file():
        raise FileNotFoundError(clip_path)

    t_mark = float(chapter.get("t_s") or 0.0)
    cap = cv2.VideoCapture(str(clip_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open clip: {clip_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
    clip_dur = total / fps if fps > 0 else 0.0

    start_s = max(0.0, t_mark - pre_s)
    end_s = min(clip_dur, t_mark + post_s) if clip_dur else t_mark + post_s
    if end_s <= start_s:
        end_s = start_s + 1.0
    start_f = int(start_s * fps)
    end_f = max(start_f + 1, int(end_s * fps))
    slow_from = max(start_s, end_s - slow_last_s)

    if output_path is None:
        out_dir = clip_path.parent / (clip_path.stem + "_cut")
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"reel_ghost_{int(t_mark * 1000):06d}.mp4"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"cannot write {output_path}")

    if timeline is None:
        timeline = load_button_timeline(clip_path)
    kind = str(chapter.get("kind") or "chapter")
    label = str(chapter.get("label") or "")
    score = _score_line(situation)
    written = 0
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)
    for idx in range(start_f, min(end_f, total if total else end_f)):
        ok, bgr = cap.read()
        if not ok or bgr is None:
            break
        if bgr.shape[1] != width or bgr.shape[0] != height:
            bgr = cv2.resize(bgr, (width, height))
        abs_t = idx / fps
        bodies = precursor_at(timeline, abs_t)
        body_line = ""
        if bodies:
            name, prec = bodies[0]
            body_line = f"BODY -{int(round(prec))}ms {name.upper()}"
        hud = _draw_hud(
            bgr,
            kind=kind,
            label=label,
            score=score,
            held=held_at(timeline, abs_t),
            t_s=abs_t - start_s,
            duration_s=end_s - start_s,
            body={n for n, _ in bodies},
            body_line=body_line,
        )
        repeats = 1
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
    binds = _binds_for_cut(timeline, chapter)
    receipt = ReelReceipt(
        session_id=session_id,
        source_clip=str(clip_path),
        source_t_s=t_mark,
        output_path=str(output_path),
        created_ns=now_ns(),
        completed_ns=now_ns(),
        status="completed",
        game_profile=game_profile,
        chapter_kind=kind,
        chapter_label=label,
        renderer="ghost_cut",
        metadata={
            "renderer": "ghost_cut",
            "pre_s": pre_s,
            "post_s": post_s,
            "slow_last_s": slow_last_s,
            "frames": written,
            "duration_s": round(duration_out, 3),
            "score": score,
            "ghost_events": len(timeline),
            "binds": binds,
            "imu_bodied": any(b.get("imu_precursor_ms") is not None for b in binds),
        },
    )
    receipt_path = write_receipt(output_path, receipt)
    log.info("Ghost Cut: %s -> %s (%d frames, %d ghosts)", clip_path.name, output_path.name, written, len(timeline))
    return GhostCutResult(output_path=output_path, receipt_path=receipt_path, frames=written, duration_s=duration_out)
