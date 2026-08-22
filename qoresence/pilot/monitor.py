"""Pilot monitor — localhost HTTP sampler. Never opens capture."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import closeout, metrics

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8765"
DEFAULT_INTERVAL = 2.0
_SECRET_KEYS = ("token", "api_key", "apikey", "authorization", "secret", "password")

_runtime: PilotMonitor | None = None


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if any(s in lk for s in _SECRET_KEYS):
                out[k] = "[redacted]"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


def _get_json(url: str, timeout: float) -> tuple[dict[str, Any] | None, str | None, float]:
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        dt = time.monotonic() - t0
        if isinstance(raw, dict):
            return _redact(raw), None, dt
        return None, "non-object json", dt
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        return None, f"{type(e).__name__}: {e}", time.monotonic() - t0


def _list_clips(clips_dir: Path) -> set[str]:
    if not clips_dir.is_dir():
        return set()
    out: set[str] = set()
    try:
        for p in clips_dir.rglob("*.mp4"):
            out.add(str(p).replace("\\", "/"))
    except OSError:
        return out
    return out


class PilotMonitor:
    def __init__(
        self,
        url: str = DEFAULT_URL,
        *,
        interval_s: float = DEFAULT_INTERVAL,
        out_dir: str | Path = "logs/pilot",
        clips_dir: str | Path = "clips",
        warm_up_s: float = metrics.WARM_UP_S,
        duration_s: float = 0.0,
    ) -> None:
        self.url = url.rstrip("/")
        self.interval_s = float(interval_s)
        self.out_dir = Path(out_dir)
        self.clips_dir = Path(clips_dir)
        self.warm_up_s = float(warm_up_s)
        self.duration_s = float(duration_s)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.session_path = self.out_dir / f"session_{stamp}.jsonl"
        self.events_path = self.out_dir / f"events_{stamp}.jsonl"
        self.closeout_json: Path | None = None
        self.closeout_md: Path | None = None
        self._err_logs = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="pilot-monitor", daemon=True)
        self._thread.start()
        log.info("pilot_monitor writing %s", self.session_path)

    def stop(self, timeout_s: float = 2.0) -> Path | None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(0.1, timeout_s))
            self._thread = None
        return self._write_closeout()

    def _append(self, path: Path, rec: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def _loop(self) -> None:
        t_start = time.monotonic()
        freeze_s = 0
        no_s = 0
        unlocked_s = 0.0
        prev_score: tuple[int, int] | None = None
        known_clips = _list_clips(self.clips_dir)
        graph_err_s = 0
        prev_frames: int | None = None
        timeout = min(2.0, max(0.4, self.interval_s))

        while not self._stop.is_set():
            now = time.monotonic()
            if self.duration_s > 0 and (now - t_start) >= self.duration_s:
                break
            elapsed = now - t_start
            flags: list[str] = []
            err: str | None = None
            health, herr, hdt = _get_json(self.url + "/health", timeout)
            if health is None:
                flags.append("DECK_DOWN")
                err = herr
                if self._err_logs < 3:
                    log.info("pilot_monitor deck_unreachable: %s", herr)
                    self._err_logs += 1
                rec = {
                    "ts": datetime.now(UTC).isoformat(),
                    "clock_ns": time.monotonic_ns(),
                    "video_age_s": None,
                    "frames": None,
                    "has_frame": False,
                    "score_home": None,
                    "score_away": None,
                    "score_vlm_locked": None,
                    "drive_phase": None,
                    "climax": None,
                    "flags": flags + ["FREEZE"],
                    "freeze_kind": "deck_lock",
                    "clips_n": len(known_clips),
                    "society_veto_n": 0,
                    "society_receipts": None,
                    "err": err,
                    "health_s": round(hdt, 3),
                }
                self._append(self.session_path, rec)
                self._stop.wait(self.interval_s)
                continue
            self._err_logs = 0

            st = health.get("state") if isinstance(health.get("state"), dict) else {}
            vid = st.get("video") if isinstance(st.get("video"), dict) else {}
            sit = st.get("situation") if isinstance(st.get("situation"), dict) else {}
            tl = st.get("timeline") if isinstance(st.get("timeline"), dict) else {}
            soc = health.get("society") if isinstance(health.get("society"), dict) else {}

            sit2 = None
            sdt = 0.0
            if not sit:
                sit2, serr, sdt = _get_json(self.url + "/api/situation", timeout)
                if sit2 is None and serr:
                    graph_err_s += 1
                    if graph_err_s >= 2 or sdt > metrics.GRAPH_TIMEOUT_S:
                        flags.append("GRAPH_STALL")
                else:
                    graph_err_s = 0
                    sit = (sit2.get("situation") if isinstance(sit2, dict) else None) or sit2 or {}
                    if isinstance(sit2, dict) and isinstance(sit2.get("timeline"), dict):
                        tl = sit2.get("timeline") or tl
            if hdt > metrics.GRAPH_TIMEOUT_S or sdt > metrics.GRAPH_TIMEOUT_S:
                if "GRAPH_STALL" not in flags:
                    flags.append("GRAPH_STALL")

            has_frame = bool(vid.get("has_frame"))
            try:
                frames = int(vid.get("frames") or 0)
            except (TypeError, ValueError):
                frames = 0
            age = vid.get("age_s")
            try:
                age_f = float(age) if age is not None else None
            except (TypeError, ValueError):
                age_f = None

            freeze_s = metrics.freeze_streak(has_frame, age_f, freeze_s)
            freeze_kind = None
            if metrics.freeze_flag(freeze_s):
                flags.append("FREEZE")
                freeze_kind = metrics.classify_freeze(
                    has_frame=has_frame,
                    age_s=age_f,
                    frames=frames,
                    prev_frames=prev_frames,
                    graph_stall="GRAPH_STALL" in flags,
                    deck_down=False,
                )
                flags.append(freeze_kind)
            prev_frames = frames
            no_s = metrics.no_frame_streak(has_frame, frames, no_s)
            if metrics.no_frame_flag(no_s, elapsed, self.warm_up_s):
                flags.append("NO_FRAMES")

            home = sit.get("home_score") if isinstance(sit, dict) else None
            away = sit.get("away_score") if isinstance(sit, dict) else None
            locked = sit.get("score_vlm_locked") if isinstance(sit, dict) else None
            if locked is None and isinstance(sit, dict):
                locked = sit.get("scoreboard_locked")
            pair = metrics.score_pair(home, away)
            unlocked_s = metrics.unlocked_tick(
                pair is not None, locked, unlocked_s, self.interval_s
            )
            if metrics.unlocked_flag(unlocked_s):
                flags.append("SCORE_UNLOCKED_LONG")
            old_score = prev_score
            if metrics.score_changed(old_score, pair):
                flags.append("SCORE_DELTA")
                if metrics.score_decreased(old_score, pair):
                    flags.append("SCORE_ROLLBACK")
                line = f"{datetime.now(UTC).strftime('%H:%M:%S')} {old_score}→{pair}"
                self._append(
                    self.events_path,
                    {
                        "ts": datetime.now(UTC).isoformat(),
                        "kind": "SCORE_DELTA",
                        "line": line,
                        "prev": old_score,
                        "cur": pair,
                        "rollback": metrics.score_decreased(old_score, pair),
                    },
                )
            if pair is not None:
                prev_score = pair

            now_clips = _list_clips(self.clips_dir)
            new = sorted(now_clips - known_clips)
            if new:
                flags.append("CLIP_NEW")
                known_clips = now_clips

            dg = tl.get("drive_graph") if isinstance(tl, dict) else None
            phase = None
            climax = None
            if isinstance(dg, dict):
                phase = dg.get("phase")
                cl = dg.get("climax") if isinstance(dg.get("climax"), dict) else {}
                climax = cl.get("score")

            rec = {
                "ts": datetime.now(UTC).isoformat(),
                "clock_ns": time.monotonic_ns(),
                "video_age_s": age_f,
                "frames": frames,
                "has_frame": has_frame,
                "score_home": pair[0] if pair else None,
                "score_away": pair[1] if pair else None,
                "score_prev": list(old_score) if old_score and "SCORE_DELTA" in flags else None,
                "score_vlm_locked": locked,
                "nameplate_ambiguous": bool(sit.get("nameplate_ambiguous"))
                if isinstance(sit, dict)
                else False,
                "drive_phase": phase,
                "climax": climax,
                "flags": flags,
                "freeze_kind": freeze_kind,
                "clips_n": len(known_clips),
                "new_clips": new,
                "society_veto_n": 0,
                "society_receipts": soc.get("receipts"),
                "err": err,
                "health_s": round(hdt, 3),
            }
            self._append(self.session_path, rec)
            self._stop.wait(self.interval_s)

        self._write_closeout()

    def _write_closeout(self) -> Path | None:
        if self.closeout_md and self.closeout_md.is_file():
            return self.closeout_md
        try:
            j, md, _ = closeout.write_closeout(self.session_path, events_path=self.events_path)
            self.closeout_json = j
            self.closeout_md = md
            log.info("pilot_monitor closeout %s", md)
            return md
        except Exception as e:
            log.debug("pilot closeout failed: %s", e)
            return None


def start_pilot_monitor(url: str | None = None) -> PilotMonitor | None:
    global _runtime
    raw = os.environ.get("QORESENCE_PILOT_MONITOR")
    if raw is None:
        return None
    if raw.strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if _runtime is not None:
        return _runtime
    host = url or DEFAULT_URL
    rt = PilotMonitor(host)
    rt.start()
    _runtime = rt
    return rt


def stop_pilot_monitor() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop(timeout_s=2.0)
        _runtime = None
