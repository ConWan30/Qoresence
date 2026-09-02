"""Gaming scoreboard referee via Quicksilver (same API as ClutchBot).

Classical EasyOCR misreads stylized CFB digits (20-0 → 20-20). When the
ClutchBot Quicksilver key is present, we crop the scorebug / pause plate
and ask glm-5.3-flash for a strict JSON board read.

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

from qoresence.agents.llm_client import (
    DEFAULT_BASE_URL,
    DEFAULT_VISION_MODEL,
    LLMConfig,
    _resolve_api_key,
)
from qoresence.security.redact import safe_http_body as _safe_http_body
from qoresence.vision.scorebug_crops import (
    CFB_PRIMARY_SCOREBUG,
    confirm_scorebug_bands,
    crop_misses_scorebug,
    is_madden_profile,
    primary_scorebug_crop,
)

log = logging.getLogger(__name__)

SCOREBOARD_MODEL = os.environ.get("QORESENCE_SCOREBOARD_VLM_MODEL", DEFAULT_VISION_MODEL)
# Smarter DeepSeek cadence (not every frame):
# - gameplay: ~1.5–2 Hz board (default 0.6s min is too hot; use 1.5s)
# - menu/hub: sparse
# - force on score/menu transitions from caller
_GAMEPLAY_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_INTERVAL", "1.5"))
_MENU_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_MENU_INTERVAL", "8.0"))
# Terminal seeing-path HTTP — HOLD, do not urllib-retry, do not POST again this process.
_HOLD_HTTP = frozenset({400, 401, 402, 429})
# 26px 360p HUD strips look like tickers to the VLM. Upscale height only.
_MIN_CROP_H = 96

# CFB 26/27: in-game scorebug is the red/blue bar (~y 0.78–0.93).
# The national ticker / other-games crawl is the last ~7% (y > 0.93).
TICKER_CUT_Y = 0.93
# (x1, x2, y1, y2) fractions — CFB default; Madden overrides via primary_scorebug_crop.
_SCOREBUG_FRAC = CFB_PRIMARY_SCOREBUG
_PAUSE_FRAC = (0.22, 0.78, 0.12, 0.52)

_PROMPT = """You are a football scoreboard identity engine for EA College Football or Madden NFL.
Look at THIS match's primary in-game scorebug or pause score plate only.
Return STRICT JSON, no markdown:
{"home_score": <int|null>, "away_score": <int|null>, "home_left": <bool|null>,
 "left_team": "<wordmark or null>", "left_score": <int|null>,
 "left_color": "<jersey/bug color>", "left_logo": "<mascot/logo>",
 "right_team": "<wordmark or null>", "right_score": <int|null>,
 "right_color": "<jersey/bug color>", "right_logo": "<mascot/logo>",
 "quarter": <1-4|null>, "clock": "<m:ss>"|null, "down": <1-4|null>,
 "yards_to_go": <int|null>, "play_clock": <int|null>, "paused": <bool>,
 "visible_control": {"button": "<Cross|Circle|Square|Triangle|L1|R1|L2|R2|null>",
  "glyph": "<mark or null>", "prompt": "<on-screen verb or null>"}}
Rules:
- Read ONLY the two LARGE score digits next to the two team marks on THIS crop. Ignore everything else.
- SPATIAL LAW (never violate): left_team / left_score are on the LEFT side of this image; right_team / right_score are on the RIGHT side. Never swap sides.
- Example: CAR · 7 on the left and NO · 0 on the right → left_team=CAR, left_score=7, right_team=NO, right_score=0. Painting 7 onto NO or swapping scores is WRONG.
- Do NOT remap via home/away if that would invert left↔right. left_* stays left, right_* stays right.
- home_score / away_score are HOME vs AWAY (not left vs right). Set home_left true only if the HOME team wordmark is on the LEFT; still keep left_* = left side of image.
- IGNORE the bottom ticker / crawl / "scores around the country" strip. Those are OTHER games. Never copy a ticker pair.
- If you see many small scores in a row, that is a ticker — set scores null rather than using it.
- Madden NFL: the compact lower-center HUD (two team marks + TWO large scores + down/distance + play clock) IS this match's scorebug. It is not a ticker. Read it.
- A ticker is a ROW OF MANY small scores. Two scores next to two team logos is the match.
- visible_control: if a DualSense callout is on this crop (Cross/Circle/Square/Triangle/L1/R1/L2/R2 plus an on-screen verb like Preplay/Snap), fill it. Else nulls.
- Bind EACH SIDE: the name, jersey/scorebug color, and logo on that side stay with THAT side's score. Never swap a mustang onto a cardinal, or blue onto a red bug.
- left_color / right_color: dominant jersey or bug color (blue, red, crimson, orange, gold, purple, green, black, white, maroon, navy).
- left_logo / right_logo: mascot/mark (eagle, horse, star, fleur-de-lis, mustang, cardinal, …) not a URL.
- Madden: use NFL abbreviations when readable (KC, PHI, CAR, NO, DAL, SF, …). NCAA: school wordmarks (OU, LOU, …).
- Read the BIG score digits only (not records, TOTAL, play clock, ticker).
- 0 is valid when clearly shown. If either large score is unreadable, return null for ALL score fields (home_score, away_score, left_score, right_score). Never invent 0-0 to fill gaps. Fail closed.
- Game year: read only what the wordmark shows (e.g. Madden NFL 26). Do not guess Madden NFL 27. Null/unset is better than a wrong year.
"""


def infer_vlm_source(model: str | None = None, base_url: str | None = None) -> str:
    """Map model / endpoint to a seeing-path ConfirmTicket source."""
    m = str(model or "").lower()
    b = str(base_url or "").lower()
    if "gemini" in m:
        return "gemini"
    if "quicksilver" in m or "quicksilverpro" in b:
        return "quicksilver"
    if "deepseek" in m or "deepseek.com" in b:
        return "deepseek"
    return "quicksilver"


class ScoreboardVlmReferee:
    """Sparse Quicksilver scoreboard reads → last JSON result."""

    def __init__(self) -> None:
        env = os.environ.get("QORESENCE_SCOREBOARD_VLM", "1").strip().lower()
        self.enabled = env in {"1", "true", "yes", "on"}
        cfg = LLMConfig.from_scoreboard_vlm()
        self.model = os.environ.get("QORESENCE_SCOREBOARD_VLM_MODEL") or cfg.model
        self.base_url = str(cfg.base_url or DEFAULT_BASE_URL).rstrip("/")
        self._api_key = _resolve_api_key(cfg.api_key, cfg.api_key_file)
        if self.enabled and not self._api_key:
            log.info("Scoreboard VLM disabled — no Quicksilver API key")
            self.enabled = False
        self._lock = threading.Lock()
        self._inflight = False
        self._inflight_since = 0.0
        self._last_call = 0.0
        self._last: dict[str, Any] | None = None
        self._last_raw = ""
        self._last_reason: str = "tick"
        self._last_http_status: int | None = None
        self._last_result_ts: float = 0.0
        self._calls = 0
        self._last_crop_wh: tuple[int, int] | None = None
        self._last_crop_refuse: str | None = None
        self._last_crop_kind: str = ""
        self._held = False

    def stats(self) -> dict[str, Any]:
        raw = self._last_raw or ""
        return {
            "enabled": self.enabled,
            "model": self.model,
            "base_url": self.base_url,
            "has_result": self._last is not None,
            "last": self._last,
            "last_reason": self._last_reason,
            "last_http_status": self._last_http_status,
            "vlm_status": self.vlm_status(),
            "last_raw_preview": raw[:200].replace("\n", " ") if raw else "",
            "last_crop_wh": list(self._last_crop_wh) if self._last_crop_wh else None,
            "last_crop_kind": self._last_crop_kind or None,
            "last_crop_refuse": self._last_crop_refuse,
            "calls": self._calls,
            "held": self._held,
            "gameplay_interval_s": _GAMEPLAY_INTERVAL_S,
            "menu_interval_s": _MENU_INTERVAL_S,
        }

    def get_last(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._last) if self._last else None

    def last_crop_refuse(self) -> str | None:
        """Why the last confirm crop is not a scorebug. None = may mint."""
        with self._lock:
            return self._last_crop_refuse

    def is_held(self) -> bool:
        """True after a terminal HTTP HOLD. Observation only — no bus emit."""
        lock = getattr(self, "_lock", None)
        if lock is None:
            return bool(getattr(self, "_held", False))
        with lock:
            return bool(getattr(self, "_held", False))

    def vlm_status(self) -> str:
        """Classify the last VLM outcome. Observation only — no bus emit, no bodies."""
        from qoresence.vision.board_why import classify_vlm_status, vlm_last_grounded

        with self._lock:
            last = dict(self._last) if self._last else None
            http = self._last_http_status
            last_ts = self._last_result_ts
            has_key = bool(self._api_key)
        age_s = (time.time() - last_ts) if last is not None and last_ts else None
        grounded = vlm_last_grounded(last) if last is not None else None
        return classify_vlm_status(
            has_key=has_key,
            http_status=http,
            last=last,
            age_s=age_s,
            grounded=grounded,
        )

    def _hold_on_http(self, code: int, body: str = "") -> None:
        """Fail-closed on bad request / auth / quota. Never emit. Never mint last-good."""
        with self._lock:
            self._held = True
            self._last_http_status = int(code)
            self._last = None
            self._last_result_ts = 0.0
        # Drop last_confirm outside the referee lock. Never emit. Human HOLD beats PASS.
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            get_ticket_book().drop_last_confirm()
        except Exception:
            pass
        if code == 400:
            log.warning(
                "scoreboard VLM HTTP 400 — HOLD seeing-path (bad request) body=%s",
                _safe_http_body(body),
            )
        elif code == 402:
            log.warning("scoreboard VLM HTTP 402 — HOLD seeing-path (no credit)")
        elif code == 429:
            log.warning("scoreboard VLM HTTP 429 — HOLD seeing-path (quota)")
        elif code == 401:
            log.warning("scoreboard VLM HTTP 401 — HOLD seeing-path (auth)")
        else:
            log.warning("scoreboard VLM HTTP %s — HOLD seeing-path", code)

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
        if self.is_held():
            return
        try:
            from qoresence.graphs.look_gate import permit_confirm_look

            if not permit_confirm_look(reason=reason, force=force, has_frame=True):
                return
        except Exception:
            pass
        gst = (game_state or "").lower()
        is_gameplay = gst in {"gameplay", "playing", "in_game", ""}
        profile_lower = str(game_profile or "").lower()
        title_lower = str(game_title or "").lower()
        is_football = any(
            kw in profile_lower or kw in title_lower
            for kw in ("football", "cfb", "madden", "ncaa")
        )
        if force or reason in {"score_changed", "menu_exit", "first_lock"}:
            interval = 0.0
        elif is_gameplay or is_football:
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
                        self._last_result_ts = time.time()
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
    def _prepare_crop(src: np.ndarray) -> np.ndarray:
        """Upscale a thin HUD strip. Never crush height."""
        out = src
        mh, mw = out.shape[:2]
        if mw > 960 and mh >= _MIN_CROP_H:
            sc = 960 / mw
            out = cv2.resize(out, (960, max(8, int(mh * sc))))
            mh, mw = out.shape[:2]
        if mh < _MIN_CROP_H and mh > 0:
            sc = _MIN_CROP_H / float(mh)
            out = cv2.resize(
                out,
                (max(8, int(round(mw * sc))), _MIN_CROP_H),
                interpolation=cv2.INTER_CUBIC,
            )
        return out

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
        # Gameplay: profile-aware scorebug. Never stitch pause+bottom.
        # Madden/CFB confirm: scorebug bands only — never the mid-frame pause
        # plate (player CU). Prefer the first band that looks like a scorebug.

        is_madden = is_madden_profile(game_profile)
        is_cfb = cls._is_cfb_context(game_profile, game_title)

        effective_profile = game_profile
        if is_cfb and not is_madden:
            effective_profile = "cfb_27"
        elif is_cfb and is_madden:
            effective_profile = "cfb_27"

        if is_madden or is_cfb:
            fallback: np.ndarray | None = None
            for frac in confirm_scorebug_bands(effective_profile):
                raw = cls._slice(frame, frac)
                if raw is None:
                    continue
                out = cls._prepare_crop(raw)
                if crop_misses_scorebug(out) is None:
                    return out
                if fallback is None:
                    fallback = out
            return fallback

        scorebug = primary_scorebug_crop(effective_profile)
        src = cls._slice(frame, _PAUSE_FRAC if menu else scorebug)
        if src is None:
            src = cls._slice(frame, scorebug if menu else _PAUSE_FRAC)
        if src is None:
            return None
        return cls._prepare_crop(src)

    def _call_vlm(self, crop_bgr: np.ndarray) -> dict[str, Any] | None:
        refuse = crop_misses_scorebug(crop_bgr)
        kind = "scorebug" if refuse is None else str(refuse)
        try:
            self._last_crop_wh = (int(crop_bgr.shape[1]), int(crop_bgr.shape[0]))
        except Exception:
            self._last_crop_wh = None
        with self._lock:
            self._last_crop_refuse = refuse
            self._last_crop_kind = kind
        try:
            import pathlib

            logs_dir = pathlib.Path("logs")
            logs_dir.mkdir(exist_ok=True)
            cv2.imwrite(str(logs_dir / "vlm_last_crop.jpg"), crop_bgr)
        except Exception:
            pass
        ok, buf = cv2.imencode(".jpg", crop_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
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
            "max_tokens": 400,
            "response_format": {"type": "json_object"},
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
        # DeepSeek thinking is ON by default and can empty content (HTTP 200).
        if "deepseek" in str(self.model).lower():
            body["thinking"] = {"type": "disabled"}
        # Prefer requests (urllib got 403 on Quicksilver vision for some envs)
        try:
            import requests

            r = requests.post(url, headers=headers, json=body, timeout=14)
            log.info("scoreboard VLM HTTP %d", r.status_code)
            if r.status_code in _HOLD_HTTP:
                err_body = ""
                if r.status_code == 400:
                    try:
                        err_body = r.text
                    except Exception:
                        err_body = ""
                self._hold_on_http(r.status_code, body=err_body)
                return None
            with self._lock:
                self._last_http_status = r.status_code
            if r.status_code != 200:
                # Known HTTP from requests — do not urllib-retry (that was the storm).
                return None
            data = r.json()
        except Exception as e:
            # stdlib fallback only when requests is missing or the socket failed
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
                    log.info("scoreboard VLM HTTP %d", code)
                    if code in _HOLD_HTTP:
                        self._hold_on_http(code)
                        return None
                    with self._lock:
                        self._last_http_status = code
                    raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
            except urllib.error.HTTPError as http_err:
                log.info("scoreboard VLM HTTP %d (error)", http_err.code)
                err_body = ""
                if http_err.code == 400:
                    try:
                        err_body = http_err.read().decode("utf-8", errors="replace")
                    except Exception:
                        err_body = ""
                if http_err.code in _HOLD_HTTP:
                    self._hold_on_http(http_err.code, body=err_body)
                    return None
                with self._lock:
                    self._last_http_status = http_err.code
                log.warning("scoreboard VLM HTTP error: %s / %s", e, http_err)
                return None
            except Exception as e2:
                log.warning("scoreboard VLM HTTP failed: %s / %s", e, e2)
                return None
        choice = (data.get("choices") or [{}])[0]
        text, finish = self._choice_text(choice)
        preview = str(text)[:200].replace("\n", " ")
        if preview:
            self._last_raw = str(text)[:800]
        if not str(text).strip():
            msg = choice.get("message") or {}
            log.info(
                "scoreboard VLM HTTP 200 empty content finish=%s keys=%s",
                finish,
                list(msg.keys()) if isinstance(msg, dict) else [],
            )
            return None
        parsed = self._parse_json(str(text))
        if parsed is None:
            log.info(
                "scoreboard VLM HTTP 200 parse fail finish=%s last_raw: %s",
                finish,
                preview,
            )
        return parsed

    @staticmethod
    def _choice_text(choice: dict[str, Any]) -> tuple[str, str]:
        """DeepSeek-v4 vision often fills reasoning_content and leaves content empty."""
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict):
            msg = {}
        content = str(msg.get("content") or "").strip()
        reasoning = str(msg.get("reasoning_content") or "").strip()
        finish = str((choice or {}).get("finish_reason") or "")
        if "{" in content:
            return content, finish
        if "{" in reasoning:
            return reasoning, finish
        return content or reasoning, finish

    @staticmethod
    def first_json_object(text: str) -> dict[str, Any] | None:
        """Extract the first decodable JSON object from chatty VLM text."""
        s = str(text or "").strip()
        if not s:
            return None
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
            s = re.sub(r"\s*```\s*$", "", s).strip()
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(s):
            start = s.find("{", idx)
            if start < 0:
                return None
            try:
                obj, _end = decoder.raw_decode(s, start)
            except json.JSONDecodeError:
                idx = start + 1
                continue
            if isinstance(obj, dict):
                return obj
            idx = start + 1
        return None

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any] | None:
        obj = ScoreboardVlmReferee.first_json_object(text)
        if obj is None:
            return None
        out: dict[str, Any] = {}
        for k in (
            "home_score",
            "away_score",
            "quarter",
            "down",
            "yards_to_go",
            "play_clock",
            "left_score",
            "right_score",
        ):
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
        vc = obj.get("visible_control")
        if isinstance(vc, dict):
            button = vc.get("button")
            glyph = vc.get("glyph")
            prompt = vc.get("prompt")
            out["visible_control"] = {
                "button": str(button).strip() if button not in (None, "", "null") else None,
                "glyph": str(glyph).strip() if glyph not in (None, "", "null") else None,
                "prompt": str(prompt).strip() if prompt not in (None, "", "null") else None,
            }
        else:
            out["visible_control"] = None
        # sanity
        hs, aws = out.get("home_score"), out.get("away_score")
        if hs is not None and not (0 <= hs <= 99):
            out["home_score"] = None
        if aws is not None and not (0 <= aws <= 99):
            out["away_score"] = None
        ls, rs = out.get("left_score"), out.get("right_score")
        if ls is not None and not (0 <= ls <= 99):
            out["left_score"] = None
        if rs is not None and not (0 <= rs <= 99):
            out["right_score"] = None
        return out


_vlm: ScoreboardVlmReferee | None = None
_vlm_lock = threading.Lock()


def get_scoreboard_vlm() -> ScoreboardVlmReferee:
    global _vlm
    with _vlm_lock:
        if _vlm is None:
            _vlm = ScoreboardVlmReferee()
        ref = _vlm
    try:
        from qoresence.vision.scoreboard_extract_why import ensure_wrapped

        ensure_wrapped()
    except Exception:
        pass
    return ref
