"""Gaming scoreboard referee via Quicksilver vision (Gemini).

Classical EasyOCR misreads stylized CFB digits (20-0 → 20-20). When a
Quicksilver key is present, we crop the scorebug / pause plate and ask
gemini-3.5-flash-lite for a strict JSON board read.

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

log = logging.getLogger(__name__)

SCOREBOARD_MODEL = os.environ.get("QORESENCE_SCOREBOARD_VLM_MODEL", "gemini-3.5-flash-lite")
# Smarter Gemini cadence (not every frame):
# - gameplay: ~1.5–2 Hz board (default 0.6s min is too hot; use 1.5s)
# - menu/hub: sparse
# - force on score/menu transitions from caller
_GAMEPLAY_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_INTERVAL", "1.5"))
_MENU_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_MENU_INTERVAL", "8.0"))

_PROMPT = """You are a football scoreboard OCR engine for EA College Football / NCAA.
Look ONLY at the scoreboard or pause score plate. Return STRICT JSON, no markdown:
{"home_score": <int|null>, "away_score": <int|null>, "home_left": <bool|null>,
 "quarter": <1-4|null>, "clock": "<m:ss>"|null, "down": <1-4|null>,
 "yards_to_go": <int|null>, "play_clock": <int|null>, "paused": <bool>}
Rules:
- Report home_score as the HOME team's score and away_score as the AWAY team's score.
- By convention the AWAY team is on the LEFT and the HOME team is on the RIGHT.
- If the HOME team is clearly on the LEFT (e.g. HOME label or team name), set home_left to true.
- Read the BIG score digits only (not team records, TOTAL column, play clock, down).
- 0 is a valid score. Prefer 20-0 over inventing 20-20.
- If unsure of a field use null. Never invent a close score when digits are clear.
- If this is a PAUSED menu with large center scores, still fill home/away.
"""


class ScoreboardVlmReferee:
    """Sparse Gemini scoreboard reads → last JSON result."""

    def __init__(self) -> None:
        env = os.environ.get("QORESENCE_SCOREBOARD_VLM", "1").strip().lower()
        self.enabled = env in {"1", "true", "yes", "on"}
        self.model = SCOREBOARD_MODEL
        self.base_url = (os.environ.get("QUICKSILVER_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        key_file = os.environ.get("QUICKSILVER_API_KEY_FILE") or (
            ".secrets/quicksilver_clutchbot.key"
            if __import__("pathlib").Path(".secrets/quicksilver_clutchbot.key").exists()
            else None
        )
        self._api_key = _resolve_api_key(os.environ.get("QUICKSILVER_API_KEY"), key_file)
        if self.enabled and not self._api_key:
            log.info("Scoreboard VLM disabled — no Quicksilver API key")
            self.enabled = False
        self._lock = threading.Lock()
        self._inflight = False
        self._last_call = 0.0
        self._last: dict[str, Any] | None = None
        self._last_raw = ""
        self._last_reason: str = "tick"
        self._calls = 0

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "model": self.model,
            "has_result": self._last is not None,
            "last": self._last,
            "last_reason": self._last_reason,
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
            if self._inflight:
                return
            if not force and (now - self._last_call) < interval:
                return
            self._inflight = True
            self._last_call = now
            self._last_reason = reason
        crop = self._crop(frame)
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
            except Exception as e:
                log.debug("scoreboard VLM failed: %s", e)
            finally:
                with self._lock:
                    self._inflight = False

        threading.Thread(target=_run, name="scoreboard-vlm", daemon=True).start()

    @staticmethod
    def _crop(frame: np.ndarray) -> np.ndarray | None:
        h, w = frame.shape[:2]
        if h < 40 or w < 40:
            return None
        # Prefer center pause plate + bottom scorebug composite strip
        crops = [
            frame[int(h * 0.12) : int(h * 0.55), int(w * 0.22) : int(w * 0.78)],
            frame[int(h * 0.78) : int(h * 0.98), int(w * 0.20) : int(w * 0.80)],
        ]
        # Stitch vertically if both valid
        valid = [c for c in crops if c.size > 0 and c.shape[0] > 8 and c.shape[1] > 8]
        if not valid:
            return None
        if len(valid) == 1:
            out = valid[0]
        else:
            # resize to same width
            ww = min(c.shape[1] for c in valid)
            resized = [
                cv2.resize(c, (ww, max(8, int(c.shape[0] * ww / c.shape[1])))) for c in valid
            ]
            out = np.vstack(resized)
        # Cap size for API
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
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:180]}")
            data = r.json()
        except Exception as e:
            # stdlib fallback
            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=14) as resp:
                    raw = resp.read().decode("utf-8", errors="replace")
                data = json.loads(raw)
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
            out["home_left"] = bool(home_left) and str(home_left).lower() not in {"0", "false", "no", "null", "none"}
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
