"""Native Retina Monitor window — Windows-first via OpenCV HighGUI.

Blits FrameHub frames (no JPEG, no second capture). Optional situation strip
via HTTP poll of Deck /api/situation.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

WINDOW_TITLE = "Retina Monitor — local frames (not OBS Preview)"

# HUD layout presets
PRESETS = ("minimal", "situation", "full")
_PRESET_LABELS = {"minimal": "MIN", "situation": "SIT", "full": "FULL"}


def _next_preset(preset: str) -> str:
    """Cycle to the next preset (used by keyboard shortcut)."""
    try:
        idx = PRESETS.index(preset)
    except ValueError:
        return "situation"
    return PRESETS[(idx + 1) % len(PRESETS)]


def _downscale(frame: np.ndarray, max_width: int) -> np.ndarray:
    if max_width <= 0 or frame.shape[1] <= max_width:
        return frame
    import cv2

    scale = max_width / float(frame.shape[1])
    nh = max(1, int(frame.shape[0] * scale))
    return cv2.resize(frame, (max_width, nh), interpolation=cv2.INTER_LINEAR)


def _fetch_situation(url: str, timeout: float = 0.4) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, dict):
            sit = data.get("situation") or (data.get("state") or {}).get("situation")
            if isinstance(sit, dict):
                return sit
            if data.get("type") == "snapshot" and isinstance(data.get("situation"), dict):
                return data["situation"]
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    except Exception:
        return None


def _fmt_situation(sit: dict[str, Any] | None) -> str:
    if not sit:
        return "situation: —"
    hs, aws = sit.get("home_score"), sit.get("away_score")
    sc = f"{hs}-{aws}" if hs is not None and aws is not None else "—-—"
    q = sit.get("quarter")
    d, y = sit.get("down"), sit.get("yards_to_go")
    parts = [sc]
    if q is not None:
        parts.append(f"Q{q}")
    if d is not None:
        parts.append(f"{d}&{y if y is not None else '?'}")
    cat = sit.get("game_category") or sit.get("game_state") or ""
    if cat:
        parts.append(str(cat))
    return "  ·  ".join(parts)


def _fmt_controller_hud() -> str:
    """Thin InputRing + IVC strip (empty if controller/IVC off)."""
    try:
        from qoresence.sync.input_ring import get_input_ring
        from qoresence.sync.ivc import get_last_coupling

        btns = get_input_ring().latest_buttons()
        coup = get_last_coupling()
        c = float(coup.get("coupling") or 0.0)
        seq = coup.get("frame_seq") or 0
        btn_s = "+".join(btns[:6]) if btns else "—"
        return f"pad {btn_s}  c={c:.2f}  fs={seq}"
    except Exception:
        return ""


def _draw_hud(frame: np.ndarray, text: str, *, preset: str = "full", label: str = "") -> np.ndarray:
    import cv2

    out = frame
    if not text and preset == "minimal":
        return out
    h, w = out.shape[:2]
    bar_h = max(28, h // 18)
    # Dark bar at top
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, bar_h), (10, 14, 20), -1)
    out = cv2.addWeighted(overlay, 0.72, out, 0.28, 0)
    # Preset badge (always shown when HUD is visible)
    badge = _PRESET_LABELS.get(preset, preset.upper())
    if label:
        badge = f"{badge} · {label}"
    cv2.putText(
        out,
        f"[{badge}]",
        (w - 120, bar_h - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.35, min(0.55, w / 1400)),
        (180, 180, 180),
        1,
        cv2.LINE_AA,
    )
    if not text:
        return out
    cv2.putText(
        out,
        text[:90],
        (10, bar_h - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.45, min(0.7, w / 1200)),
        (245, 197, 66),
        1,
        cv2.LINE_AA,
    )
    return out


def run_monitor(
    *,
    stop_event: threading.Event | None = None,
    max_width: int = 1280,
    situation_url: str = "http://127.0.0.1:8765/api/situation",
    target_hz: float = 30.0,
    window_title: str = WINDOW_TITLE,
    preset: str = "full",
) -> None:
    """Blocking monitor loop (call from dedicated thread).

    HUD presets (cycle with 'p' key):
      minimal   — frame only, no overlay bar
      situation — frame + situation strip (score, quarter, down)
      full      — situation + controller + frame age/seq (default)
    """
    try:
        import cv2
    except ImportError as e:
        raise RuntimeError(
            "Retina Monitor requires opencv-python. "
            "Install: pip install 'qoresence[monitor]' or opencv-python"
        ) from e

    from qoresence.monitor.frame_hub import get_frame_hub

    hub = get_frame_hub()
    stop = stop_event or threading.Event()
    interval = 1.0 / max(5.0, min(60.0, target_hz))
    last_sit_poll = 0.0
    sit_text = "situation: —"
    last_seq = -1
    current_preset = preset if preset in PRESETS else "full"

    log.info(
        "Retina Monitor on (FrameHub ← streamer; no second capture) title=%r max_w=%s preset=%s",
        window_title,
        max_width,
        current_preset,
    )
    cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)

    try:
        while not stop.is_set():
            t0 = time.monotonic()
            frame, seq, age = hub.get_latest_meta()
            if frame is not None:
                if seq != last_seq:
                    last_seq = seq
                display = _downscale(frame, max_width)
                now = time.monotonic()
                if situation_url and (now - last_sit_poll) >= 0.5:
                    sit = _fetch_situation(situation_url)
                    sit_text = _fmt_situation(sit)
                    last_sit_poll = now
                age_ms = int(age * 1000) if age is not None else 0
                pad_hud = _fmt_controller_hud()
                # Build HUD text based on preset
                if current_preset == "minimal":
                    hud = ""
                elif current_preset == "situation":
                    hud = sit_text
                else:  # full
                    hud = f"{sit_text}   |   seq {seq}  age {age_ms}ms"
                    if pad_hud:
                        hud = f"{hud}   |   {pad_hud}"
                display = _draw_hud(display, hud, preset=current_preset)
                cv2.imshow(window_title, display)
            else:
                # Placeholder so window is visible while waiting for streamer
                blank = np.zeros((360, 640, 3), dtype=np.uint8)
                blank[:] = (18, 14, 10)
                if current_preset != "minimal":
                    blank = _draw_hud(blank, "waiting for FrameHub frames…", preset=current_preset)
                cv2.imshow(window_title, blank)

            # Esc closes monitor only; 'p' cycles HUD preset
            key = cv2.waitKey(max(1, int(interval * 1000))) & 0xFF
            if key == 27:  # Esc
                break
            if key in (ord("p"), ord("P")):
                current_preset = _next_preset(current_preset)
                log.info("Monitor HUD preset → %s", current_preset)
            # Detect user closed window (best-effort; some OpenCV builds differ)
            try:
                prop = cv2.getWindowProperty(window_title, cv2.WND_PROP_VISIBLE)
                if prop < 0:
                    break
            except Exception:
                pass
            elapsed = time.monotonic() - t0
            sleep = interval - elapsed
            if sleep > 0.001:
                time.sleep(min(sleep, 0.05))
    finally:
        try:
            cv2.destroyWindow(window_title)
        except Exception:
            pass
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        log.info("Retina Monitor stopped (streamer/Deck continue)")


def start_monitor_thread(
    *,
    max_width: int = 1280,
    situation_url: str = "http://127.0.0.1:8765/api/situation",
    target_hz: float = 30.0,
    preset: str = "full",
) -> tuple[threading.Thread, threading.Event]:
    """Start monitor on a daemon thread. Returns (thread, stop_event)."""
    stop = threading.Event()

    def _run() -> None:
        try:
            run_monitor(
                stop_event=stop,
                max_width=max_width,
                situation_url=situation_url,
                target_hz=target_hz,
                preset=preset,
            )
        except Exception as e:
            log.error("Retina Monitor failed: %s", e)

    t = threading.Thread(target=_run, name="retina-monitor", daemon=True)
    t.start()
    return t, stop
