"""Gaming scoreboard referee via DeepSeek vision.

Classical EasyOCR misreads stylized CFB digits (20-0 → 20-20). When a
DeepSeek key is present, we crop the scorebug / pause plate and ask
deepseek-v4-flash-vision-exp for a strict JSON board read.

Sparse + non-blocking: never call from the streamer grab thread.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import time
from typing import Any

import cv2
import numpy as np

from qoresence.agents.llm_client import DEFAULT_BASE_URL, _resolve_api_key
from qoresence.vision.scorebug_crops import (
    CFB_PRIMARY_SCOREBUG,
    is_madden_profile,
    primary_scorebug_crop,
)

log = logging.getLogger(__name__)

SCOREBOARD_MODEL = os.environ.get("QORESENCE_SCOREBOARD_VLM_MODEL", "deepseek-v4-flash-vision-exp")
# Smarter DeepSeek cadence (not every frame):
# - gameplay: ~1.5–2 Hz board (default 0.6s min is too hot; use 1.5s)
# - menu/hub: sparse
# - force on score/menu transitions from caller
_GAMEPLAY_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_INTERVAL", "1.5"))
_MENU_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_MENU_INTERVAL", "8.0"))

# CFB 26/27: in-game scorebug is the red/blue bar (~y 0.78–0.93).
# The national ticker / other-games crawl is the last ~7% (y > 0.93).
TICKER_CUT_Y = 0.93
# (x1, x2, y1, y2) fractions — CFB default; Madden overrides via primary_scorebug_crop.
_SCOREBUG_FRAC = CFB_PRIMARY_SCOREBUG
_PAUSE_FRAC = (0.22, 0.78, 0.12, 0.52)

_PROMPT = """You are a football scoreboard identity engine for EA College Football 27 or Madden NFL 27.
Look at THIS match's primary in-game scorebug or pause score plate only.
Return STRICT JSON, no markdown:
{"home_score": <int|null>, "away_score": <int|null>, "home_left": <bool|null>,
 "left_team": "<wordmark or null>", "left_color": "<jersey/bug color>", "left_logo": "<mascot/logo>",
 "right_team": "<wordmark or null>", "right_color": "<jersey/bug color>", "right_logo": "<mascot/logo>",
 "quarter": <1-4|null>, "clock": "<m:ss>"|null, "down": <1-4|null>,
 "yards_to_go": <int|null>, "play_clock": <int|null>, "paused": <bool>}
Rules:
- IGNORE the bottom ticker / crawl / "scores around the country" strip. Those are OTHER games. Never copy a ticker pair.
- If you see many small scores in a row, that is a ticker — set scores null rather than using it.
- Read ONLY the primary scorebug for the match on this screen (the two LARGE scores next to the two team wordmarks, with down & distance).
- Bind EACH SIDE: the name, jersey/scorebug color, and logo on that side stay with THAT side's score. Never swap a mustang onto a cardinal, or blue onto a red bug.
- left_* is the LEFT scorebug (usually away). right_* is the RIGHT scorebug (usually home).
- left_color / right_color: dominant jersey or bug color (blue, red, crimson, orange, gold, purple, green, black, white, maroon, navy).
- left_logo / right_logo: mascot/mark (eagle, horse, star, fleur-de-lis, mustang, cardinal, …) not a URL.
- Madden: use NFL abbreviations when readable (KC, PHI, DAL, SF, …). NCAA: school wordmarks (OU, LOU, …).
- home_score / away_score are HOME vs AWAY, not left vs right.
- Convention: AWAY left, HOME right. If HOME is on the LEFT, set home_left true.
- Read the BIG score digits only (not records, TOTAL, play clock, ticker).
- 0 is valid. Prefer 20-0 over inventing 20-20. Unsure → null.
"""


class ScoreboardVlmReferee:
    """Sparse DeepSeek scoreboard reads → last JSON result."""

    def __init__(self) -> None:
        env = os.environ.get("QORESENCE_SCOREBOARD_VLM", "1").strip().lower()
        self.enabled = env in {"1", "true", "yes", "on"}
        self.model = SCOREBOARD_MODEL
        self.base_url = (
            os.environ.get("DEEPSEEK_BASE_URL")
            or os.environ.get("QORESENCE_DEEPSEEK_BASE_URL")
            or "https://api.deepseek.com"
        ).rstrip("/")
        key_file = os.environ.get("DEEPSEEK_API_KEY_FILE") or (
            ".secrets/deepseek.key"
            if __import__("pathlib").Path(".secrets/deepseek.key").exists()
            else None
        )
        self._api_key = _resolve_api_key(
            os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("QORESENCE_DEEPSEEK_API_KEY"),
            key_file,
        )
        if self.enabled and not self._api_key:
            log.info("Scoreboard VLM disabled — no DeepSeek API key")
            self.enabled = False
        self._lock = threading.Lock()
        self._inflight = False
        self._inflight_since = 0.0
        self._last_call = 0.0
        self._last: dict[str, Any] | None = None
        self._last_raw = ""
        self._last_reason: str = "tick"
        self._last_http_status: int | None = None
        self._calls = 0

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "model": self.model,
            "has_result": self._last is not None,
            "last": self._last,
            "last_reason": self._last_reason,
            "last_http_status": self._last_http_status,
            "calls": self._calls,
            "gameplay_interval_s": _GAMEPLAY_INTERVAL_S,
            "menu_interval_s": _MENU_INTERVAL_S,
        }

    def get_last(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last) if self._last else None

    def schedule(
        self,
        frame: np.ndarray,
        *,
        force: bool = False,
        reason: str = "tick",
        game_state: str | None = None,
        game_profile: str | None = None,
        game_title: str | None = None,
    ) -> None:
        """Kick a background VLM read if due; never blocks.

        Cadence:
          - force / score_changed / menu_exit → immediate (if not inflight)
          - gameplay → ~1.5s (≈0.7 Hz board reads; not 60 fps)
          - menu/hub → ~8s
        """
        if not self.enabled or frame is None or getattr(frame, "size", 0) == 0:
            return
        gst = (game_state or "").lower()
        is_gameplay = gst in {"gameplay", "playing", "in_game", ""}
        if force or reason in {"score_changed", "menu_exit", "first_lock"}:
            interval = 0.0
        elif is_gameplay:
            interval = max(0.8, _GAMEPLAY_INTERVAL_S)
        else:
            interval = max(4.0, _MENU_INTERVAL_S)

        now = time.time()
        with self._lock:
            # Watchdog: clear stale inflight if thread is older than HTTP timeout (14s + 2s buffer)
            if self._inflight and (now - self._inflight_since) > 16.0:
                log.info("scoreboard VLM watchdog: clearing stale inflight (%.1fs)", now - self._inflight_since)
                self._inflight = False
            
            if self._inflight:
                log.info("scoreboard VLM skip: inflight")
                return
            if not force and (now - self._last_call) < interval:
                log.info("scoreboard VLM skip: interval (%.1fs < %.1fs)", now - self._last_call, interval)
                return
            self._inflight = True
            self._inflight_since = now
            self._last_call = now
            self._last_reason = reason
        crop = self._crop(frame, game_state=gst, game_profile=game_profile, game_title=game_title)
        if crop is None:
            with self._lock:
                self._inflight = False
            return

        def _run() -> None:
            try:
                parsed = self._call_vlm(crop)
                if parsed:
                    with self._lock:
                        self._last = parsed
                        self._calls += 1
                    log.info(
                        "scoreboard VLM → %s-%s q=%s (paused=%s reason=%s)",
                        parsed.get("home_score"),
                        parsed.get("away_score"),
                        parsed.get("quarter"),
                        parsed.get("paused"),
                        reason,
                    )
                else:
                    log.info("scoreboard VLM → null parse (reason=%s)", reason)
            except Exception as e:
                log.info("scoreboard VLM failed: %s (reason=%s)", e, reason)
            finally:
                with self._lock:
                    self._inflight = False

        threading.Thread(target=_run, name="scoreboard-vlm", daemon=True).start()

    @staticmethod
    def _slice(frame: np.ndarray, frac: tuple[float, float, float, float]) -> np.ndarray | None:
        h, w = frame.shape[:2]
        x1, x2, y1, y2 = frac
        crop = frame[int(h * y1) : int(h * y2), int(w * x1) : int(w * x2)]
        if crop.size == 0 or crop.shape[0] < 8 or crop.shape[1] < 8:
            return None
        return crop

    @staticmethod
    def _is_cfb_context(game_profile: str | None = None, game_title: str | None = None) -> bool:
        """Detect CFB/college/NCAA from profile or title."""
        profile_lower = str(game_profile or "").lower()
        title_lower = str(game_title or "").lower()
        cfb_markers = ("cfb", "college", "ncaa", "college football")
        return any(m in profile_lower or m in title_lower for m in cfb_markers)

    @classmethod
    def _crop(
        cls,
        frame: np.ndarray,
        game_state: str | None = None,
        game_profile: str | None = None,
        game_title: str | None = None,
    ) -> np.ndarray | None:
        h, w = frame.shape[:2]
        if h < 40 or w < 40:
            return None
        gst = (game_state or "").lower()
        menu = gst in {"menu", "lobby", "hub", "paused", "pause"}
        # Gameplay: profile-aware scorebug. Menu: pause plate only.
        # Never stitch pause+bottom — that used to feed Gemini the other-games crawl.
        # EXCEPTION: Madden HUD always first, even if game_state is wrongly 'menu'.
        # EXCEPTION: CFB scorebug always first, even if game_state is wrongly 'menu' (#108 pattern).
        scorebug = primary_scorebug_crop(game_profile)
        is_madden = is_madden_profile(game_profile)
        is_cfb = cls._is_cfb_context(game_profile, game_title)
        # Madden: HUD first (even on menu), pause fallback.
        # CFB: scorebug first (even on menu), pause fallback.
        # Others: menu → pause first.
        if is_madden or is_cfb:
            src = cls._slice(frame, scorebug)
            if src is None:
                src = cls._slice(frame, _PAUSE_FRAC)
        else:
            src = cls._slice(frame, _PAUSE_FRAC if menu else scorebug)
            if src is None:
                src = cls._slice(frame, scorebug if menu else _PAUSE_FRAC)
        if src is None:
            return None
        out = src
        mh, mw = out.shape[:2]
        max_dim = 640
        if max(mh, mw) > max_dim:
            sc = max_dim / max(mh, mw)
            out = cv2.resize(out, (int(mw * sc), int(mh * sc)))
        return out

    def _call_vlm(self, crop_bgr: np.ndarray) -> dict[str, Any] | None:
        ok, buf = cv2.imencode(".jpg", crop_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            return None
        b64 = base64.b64encode(buf.tobytes()).decode("ascii")
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Qoresence-ScoreboardVLM/1.0",
            "Accept": "application/json",
        }
        body = {
            "model": self.model,
            "temperature": 0.0,
            "max_tokens": 180,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
        }
        # Prefer requests (urllib got 403 on Quicksilver vision for some envs)
        try:
            import requests

            r = requests.post(url, headers=headers, json=body, timeout=14)
            with self._lock:
                self._last_http_status = r.status_code
            log.info("scoreboard VLM HTTP %d", r.status_code)
            if r.status_code == 402:
                # HTTP 402 Payment Required: clear _last to HOLD seeing-path
                with self._lock:
                    self._last = None
                log.warning("scoreboard VLM HTTP 402 — HOLD seeing-path (no credit)")
                return None
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:180]}")
            data = r.json()
        except Exception as e:
            # stdlib fallback
            import urllib.error
            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=14) as resp:
                    code = resp.getcode()
                    with self._lock:
                        self._last_http_status = code
                    log.info("scoreboard VLM HTTP %d", code)
                    if code == 402:
                        with self._lock:
                            self._last = None
                        log.warning("scoreboard VLM HTTP 402 — HOLD seeing-path (no credit)")
                        return None
                    raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
            except urllib.error.HTTPError as http_err:
                # HTTPError has a .code attribute for the HTTP status
                with self._lock:
                    self._last_http_status = http_err.code
                log.info("scoreboard VLM HTTP %d (error)", http_err.code)
                if http_err.code == 402:
                    with self._lock:
                        self._last = None
                    log.warning("scoreboard VLM HTTP 402 — HOLD seeing-path (no credit)")
                    return None
                log.warning("scoreboard VLM HTTP error: %s / %s", e, http_err)
                return None
            except Exception as e2:
                log.warning("scoreboard VLM HTTP failed: %s / %s", e, e2)
                return None
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        self._last_raw = str(text)[:500]
        return self._parse_json(str(text))

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        text = text.strip()
        # strip fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        # find first {…}
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None
        out: dict[str, Any] = {}
        for k in ("home_score", "away_score", "quarter", "down", "yards_to_go", "play_clock"):
            v = obj.get(k)
            if v is None or v == "":
                out[k] = None
                continue
            try:
                out[k] = int(v)
            except Exception:
                out[k] = None

        home_left = obj.get("home_left")
        if isinstance(home_left, bool):
            out["home_left"] = home_left
        elif isinstance(home_left, (int, float, str)):
            out["home_left"] = bool(home_left) and str(home_left).lower() not in {
                "0",
                "false",
                "no",
                "null",
                "none",
            }
        else:
            out["home_left"] = None
        # clock "4:51" → seconds
        clock = obj.get("clock")
        if isinstance(clock, str) and ":" in clock:
            try:
                mm, ss = clock.strip().split(":")[:2]
                out["clock_seconds"] = int(mm) * 60 + int(ss)
            except Exception:
                out["clock_seconds"] = None
        elif isinstance(clock, (int, float)):
            out["clock_seconds"] = int(clock)
        else:
            out["clock_seconds"] = None
        out["paused"] = bool(obj.get("paused"))
        for side_k in (
            "left_team",
            "left_color",
            "left_logo",
            "right_team",
            "right_color",
            "right_logo",
        ):
            v = obj.get(side_k)
            out[side_k] = str(v).strip() if v not in (None, "") else None
        # sanity
        hs, aws = out.get("home_score"), out.get("away_score")
        if hs is not None and not (0 <= hs <= 99):
            out["home_score"] = None
        if aws is not None and not (0 <= aws <= 99):
            out["away_score"] = None
        return out


_vlm: ScoreboardVlmReferee | None = None
_vlm_lock = threading.Lock()


def get_scoreboard_vlm() -> ScoreboardVlmReferee:
    global _vlm
    with _vlm_lock:
        if _vlm is None:
            _vlm = ScoreboardVlmReferee()
        return _vlm
