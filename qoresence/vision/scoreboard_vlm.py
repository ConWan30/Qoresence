"""Gaming scoreboard referee via Quicksilver (same API as ClutchBot).

Classical EasyOCR misreads stylized CFB digits (20-0 → 20-20). When the
ClutchBot Quicksilver key is present, we crop the scorebug / pause plate
and ask gemini-3.5-flash-lite for a strict JSON board read.

Sparse + non-blocking: never call from the streamer grab thread.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
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
# Sparse cadence (not every frame):
# - gameplay: default 6.0s (env QORESENCE_SCOREBOARD_VLM_INTERVAL still wins)
# - menu/hub: sparse
# - force on score/menu transitions from caller
_GAMEPLAY_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_INTERVAL", "6.0"))
_MENU_INTERVAL_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_MENU_INTERVAL", "8.0"))
# Terminal seeing-path HTTP — HOLD, do not urllib-retry, do not POST again this process.
# HTTP 429 is quota: soft cooldown, not a permanent process HOLD.
_HOLD_HTTP = frozenset({400, 401, 402})
_QUOTA_BACKOFF_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_429_COOLDOWN", "60.0"))
# Quicksilver Read timeout — shorter than prior 14s; env override wins.
_HTTP_TIMEOUT_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_HTTP_TIMEOUT", "14"))
# Confirm path waits for chat/visual to drop the slot. 0.05s yield meant
# scoreboard never POSTed (empty HTTP never ran; last_http_status stayed None).
_QUICKSILVER_SLOT_WAIT_S = float(
    os.environ.get("QORESENCE_SCOREBOARD_VLM_SLOT_WAIT", "8.0")
)
# SEQGATE fresh window is 8s; VLM POST can run ~14s. Heartbeat mid-flight only.
_CONFIRM_HEARTBEAT_INTERVAL_S = 3.0
_INFLIGHT_WATCHDOG_S = _HTTP_TIMEOUT_S + 2.0
# Soft budget: if a force/score_changed remint is queued while a POST is still
# inflight, abandon the stale generation after this many seconds so a fresh
# scorebug crop can mint instead of waiting the full HTTP (~14s) / watchdog (~16s).
_PENDING_REMINT_SOFT_BUDGET_S = float(
    os.environ.get("QORESENCE_SCOREBOARD_VLM_PENDING_REMINT_SOFT", "3.5")
)
_TIMEOUT_BACKOFF_BASE_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_TIMEOUT_BACKOFF", "1"))
_TIMEOUT_BACKOFF_MAX_S = float(os.environ.get("QORESENCE_SCOREBOARD_VLM_TIMEOUT_BACKOFF_MAX", "2"))
# 26px 360p HUD strips look like tickers to the VLM. Upscale height only.
_MIN_CROP_H = 96


def _refresh_confirm_clock_from_framehub() -> None:
    """Bump licensed ConfirmTicket.clock_ns from FrameHub — no remint, no new digits."""
    try:
        from qoresence.monitor.frame_hub import get_latest_stamp
        from qoresence.vision.confirm_ticket import refresh_licensed_ticket_clock

        stamp = get_latest_stamp() or {}
        clock_ns = int(stamp.get("clock_ns") or 0)
        if clock_ns <= 0:
            clock_ns = int(time.time_ns())
        refresh_licensed_ticket_clock(
            clock_ns=clock_ns,
            frame_seq=stamp.get("seq"),
        )
    except Exception:
        pass


def _refresh_confirm_clock_after_200() -> None:
    """VLM HTTP 200 must bump ConfirmTicket.clock_ns or SEQGATE goes ticket_stale.

    Empty/null parse 200s still refresh — the ticket stays licensed without remint.
    """
    _refresh_confirm_clock_from_framehub()


@contextmanager
def _confirm_clock_heartbeat_while_inflight():
    """Keep licensed ticket fresh while confirm VLM POST blocks (8s window < ~14s POST)."""
    try:
        from qoresence.vision.confirm_ticket import licensed_last_confirm

        if licensed_last_confirm() is None:
            yield
            return
    except Exception:
        yield
        return

    stop = threading.Event()

    def _loop() -> None:
        _refresh_confirm_clock_from_framehub()
        while not stop.wait(_CONFIRM_HEARTBEAT_INTERVAL_S):
            _refresh_confirm_clock_from_framehub()

    thread = threading.Thread(
        target=_loop, name="confirm-ticket-heartbeat", daemon=True
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=_CONFIRM_HEARTBEAT_INTERVAL_S + 0.5)

# CFB 26/27: in-game scorebug is the red/blue bar (~y 0.78–0.93).
# The national ticker / other-games crawl is the last ~7% (y > 0.93).
TICKER_CUT_Y = 0.93
# (x1, x2, y1, y2) fractions — CFB default; Madden overrides via primary_scorebug_crop.
_SCOREBUG_FRAC = CFB_PRIMARY_SCOREBUG
_PAUSE_FRAC = (0.22, 0.78, 0.12, 0.52)

_PROMPT = """Output ONE JSON object as the first characters. No preamble.
You are a football scoreboard identity engine for EA College Football or Madden NFL.
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
- Madden example: NO + hollow 0 on the left, IND + 22 on the right → left_team=NO, left_score=0, right_team=IND, right_score=22, home_left=false. Do not return all-nulls.
- Do NOT remap via home/away if that would invert left↔right. left_* stays left, right_* stays right.
- home_score / away_score are HOME vs AWAY (not left vs right). Set home_left true only if the HOME team wordmark is on the LEFT; still keep left_* = left side of image.
- IGNORE the bottom ticker / crawl / "scores around the country" strip. Those are OTHER games. Never copy a ticker pair.
- If you see many small scores in a row, that is a ticker — set scores null rather than using it.
- Madden NFL: the compact lower-center HUD (two team marks + TWO large scores + down/distance + play clock) IS this match's scorebug. It is not a ticker. Read it.
- A ticker is a ROW OF MANY small scores. Two scores next to two team logos is the match.
- visible_control: if a DualSense callout is on this crop (Cross/Circle/Square/Triangle/L1/R1/L2/R2 plus an on-screen verb like Preplay/Snap), fill it. Else nulls.
- paused=true ONLY for true pause/SELECT menu without a live scorebug. Preplay/Subs with down+distance and team wordmarks is gameplay — paused=false.
- Bind EACH SIDE: the name, jersey/scorebug color, and logo on that side stay with THAT side's score. Never swap a mustang onto a cardinal, or blue onto a red bug.
- left_color / right_color: dominant jersey or bug color (blue, red, crimson, orange, gold, purple, green, black, white, maroon, navy).
- left_logo / right_logo: mascot/mark (eagle, horse, star, fleur-de-lis, mustang, cardinal, …) not a URL.
- Madden: use NFL abbreviations when readable (KC, PHI, CAR, NO, DAL, SF, …). NCAA: school wordmarks (OU, LOU, …).
- Read the BIG score digits only (not records, TOTAL, play clock, ticker).
- 0 is valid when clearly shown. A hollow oval, thin ring, or "O" in a team's score slot is 0, not missing.
- Madden compact HUD: two team marks + scores on the dark bar IS this match (even if one score is 0). Do not null the whole board because one side is 0.
- If both team wordmarks are readable and only one score digit is fuzzy, still return the readable score and 0 for the hollow/empty slot next to the other wordmark.
- If you cannot see two team marks, or the crop is a ticker / player close-up, return null for ALL score fields. Never invent 0-0 to fill a blank frame. Fail closed.
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


def _record_replay_row(parsed: dict, recheck_status: str) -> None:
    """Append one surviving parse to QORESENCE_SCORE_REPLAY_LOG (JSONL).

    Default-off capture path for the scoreboard replay eval: each row carries
    the parse plus ``_observation`` source-frame metadata (seq / clock_ns /
    crop_hash / session_id) — never image bytes or credentials. Folded into a
    qoresence-score-replay-0 manifest offline via
    ``evals.scoreboard.manifest.build_manifest_from_recording``.
    """
    path = os.environ.get("QORESENCE_SCORE_REPLAY_LOG", "").strip()
    if not path:
        return
    try:
        row = dict(parsed)
        row["recorded_ns"] = time.monotonic_ns()
        row["recheck_status"] = recheck_status
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError:
        log.debug("score replay row write failed", exc_info=True)


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
        self._backoff_until = 0.0
        self._timeout_backoff_until = 0.0
        self._timeout_count = 0
        self._consecutive_timeouts = 0
        self._skip_inflight_count = 0
        self._skip_interval_count = 0
        self._pending_remint_count = 0
        self._last_timeout_ts = 0.0
        self._request_generation = 0
        # Latest force/score_changed request deferred while a VLM POST is inflight.
        self._pending_remint: dict[str, Any] | None = None
        self.recheck_enabled = os.environ.get("QORESENCE_SCORE_RECHECK", "0").lower() in {
            "1", "true", "yes", "on",
        }
        # warn-once flag shared with transition_verdict system_one calls
        self._jev_warned = [False]
        from qoresence.vision.score_recheck import ScoreRecheck

        self._score_recheck = ScoreRecheck()
        self._recheck_status = "idle"

    def stats(self) -> dict[str, Any]:
        raw = self._last_raw or ""
        now = time.time()
        with self._lock:
            inflight = bool(self._inflight)
            inflight_since = float(self._inflight_since or 0.0)
            timeout_count = int(self._timeout_count)
            skip_inflight = int(self._skip_inflight_count)
            skip_interval = int(self._skip_interval_count)
            pending_remint = int(self._pending_remint_count)
            has_pending = self._pending_remint is not None
            timeout_backoff = max(0.0, float(self._timeout_backoff_until or 0.0) - now)
            quota_backoff = max(0.0, float(self._backoff_until or 0.0) - now)
        inflight_age_s = (now - inflight_since) if inflight and inflight_since else None
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
            "inflight": inflight,
            "inflight_age_s": inflight_age_s,
            "timeout_count": timeout_count,
            "skip_inflight_count": skip_inflight,
            "skip_interval_count": skip_interval,
            "pending_remint_count": pending_remint,
            "pending_remint": has_pending,
            "http_timeout_s": _HTTP_TIMEOUT_S,
            "inflight_watchdog_s": _INFLIGHT_WATCHDOG_S,
            "pending_remint_soft_budget_s": _PENDING_REMINT_SOFT_BUDGET_S,
            "timeout_backoff_s": timeout_backoff,
            "quota_backoff_s": quota_backoff,
            "gameplay_interval_s": _GAMEPLAY_INTERVAL_S,
            "menu_interval_s": _MENU_INTERVAL_S,
            "recheck_enabled": getattr(self, "recheck_enabled", False),
            "recheck_status": getattr(self, "_recheck_status", "idle"),
        }

    def get_last(self) -> dict[str, Any] | None:
        with self._lock:
            last = copy.deepcopy(self._last) if self._last else None
        if last and getattr(self, "recheck_enabled", False):
            from qoresence.sync.digit_integrity import CONFIRM_DIGIT_MAX_AGE_NS
            from qoresence.vision.confirm_ticket import resolve_session_id

            source = last.get("_observation") or {}
            age = time.monotonic_ns() - int(source.get("clock_ns") or 0)
            if not 0 <= age <= CONFIRM_DIGIT_MAX_AGE_NS:
                return None
            if source.get("session_id") != resolve_session_id():
                return None
        return last

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

    def is_inflight(self) -> bool:
        """True while a scoreboard VLM read is scheduled or on the wire."""
        with self._lock:
            return bool(self._inflight)

    def _drain_pending_remint(self) -> None:
        """Fire one deferred force/score_changed remint after inflight clears."""
        with self._lock:
            # Tests may construct a partial referee; never AttributeError mid-drain.
            pending = getattr(self, "_pending_remint", None)
            self._pending_remint = None
            if getattr(self, "_inflight", False) or not pending:
                return
        frame = pending.get("frame")
        if frame is None or getattr(frame, "size", 0) == 0:
            return
        log.info(
            "scoreboard VLM draining pending remint (reason=%s)",
            pending.get("reason"),
        )
        self.schedule(
            frame,
            force=bool(pending.get("force", True)),
            reason=str(pending.get("reason") or "score_changed"),
            source_stamp=pending.get("source_stamp"),
            game_state=pending.get("game_state"),
            game_profile=pending.get("game_profile"),
            game_title=pending.get("game_title"),
        )

    def _in_backoff(self, now: float | None = None) -> bool:
        """True while a 429 or read-timeout cooldown is active."""
        t = time.time() if now is None else now
        lock = getattr(self, "_lock", None)

        def _check() -> bool:
            until = float(getattr(self, "_backoff_until", 0.0) or 0.0)
            tout = float(getattr(self, "_timeout_backoff_until", 0.0) or 0.0)
            if until <= 0.0 and tout <= 0.0:
                return False
            if until > 0.0 and t < until:
                return True
            if tout > 0.0 and t < tout:
                return True
            if until > 0.0 and t >= until:
                self._backoff_until = 0.0
            if tout > 0.0 and t >= tout:
                self._timeout_backoff_until = 0.0
            return False

        if lock is None:
            return _check()
        with lock:
            return _check()

    @staticmethod
    def _is_read_timeout(exc: BaseException) -> bool:
        try:
            import requests

            if isinstance(
                exc,
                (
                    requests.exceptions.Timeout,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.ConnectTimeout,
                ),
            ):
                return True
        except Exception:
            pass
        if isinstance(exc, TimeoutError):
            return True
        msg = str(exc).lower()
        return "timed out" in msg or "read timeout" in msg

    def _on_read_timeout(self) -> None:
        """Read timed out — backoff and allow next tick (inflight cleared in _run finally)."""
        now = time.time()
        with self._lock:
            self._timeout_count += 1
            self._consecutive_timeouts += 1
            self._last_timeout_ts = now
            self._last = None
            self._last_result_ts = 0.0
            exp = min(
                _TIMEOUT_BACKOFF_BASE_S * (2 ** max(0, self._consecutive_timeouts - 1)),
                _TIMEOUT_BACKOFF_MAX_S,
            )
            self._timeout_backoff_until = now + exp
            # Retry as soon as backoff ends — do not also sit the 6s interval.
            self._last_call = 0.0
        log.warning(
            "scoreboard VLM Read timed out (%.1fs) — backoff %.1fs",
            _HTTP_TIMEOUT_S,
            exp,
        )

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
        """Fail-closed on bad request / auth / no-credit. Never emit. Never mint last-good.

        HTTP 429 is not a HOLD — it routes to a soft quota cooldown.
        """
        if int(code) == 429:
            self._backoff_on_429()
            return
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
        elif code == 401:
            log.warning("scoreboard VLM HTTP 401 — HOLD seeing-path (auth)")
        else:
            log.warning("scoreboard VLM HTTP %s — HOLD seeing-path", code)

    def _backoff_on_429(self) -> None:
        """HTTP 429: skip schedule/calls for a cooldown. Do not latch process HOLD."""
        now = time.time()
        with self._lock:
            self._last_http_status = 429
            self._last = None
            self._last_result_ts = 0.0
            self._backoff_until = now + _QUOTA_BACKOFF_S
        try:
            from qoresence.vision.confirm_ticket import get_ticket_book

            get_ticket_book().drop_last_confirm()
        except Exception:
            pass
        log.warning(
            "scoreboard VLM HTTP 429 — quota backoff %.1fs (not HOLD)",
            _QUOTA_BACKOFF_S,
        )

    def _on_terminal_http(self, code: int, body: str = "") -> bool:
        """HOLD (400/401/402) or 429 backoff. True → caller returns None. Never emits."""
        c = int(code)
        if c == 429:
            self._backoff_on_429()
            return True
        if c in _HOLD_HTTP:
            self._hold_on_http(c, body=body)
            return True
        return False

    def schedule(
        self,
        frame: np.ndarray,
        *,
        force: bool = False,
        reason: str = "tick",
        source_stamp: dict[str, Any] | None = None,
        game_state: str | None = None,
        game_profile: str | None = None,
        game_title: str | None = None,
    ) -> None:
        """Kick a background VLM read if due; never blocks.

        Cadence:
          - force / score_changed / menu_exit → immediate (bypass interval)
          - if inflight, force/score_changed/menu_exit/first_lock queues a
            pending remint that fires when the in-flight POST clears
          - if pending remint is set and inflight_age > soft budget (~3.5s),
            bump request generation, clear inflight, drain remint immediately
            (do not wait full HTTP ~14s / watchdog ~16s with blank digits)
          - gameplay → default 6.0s (env override wins; not 60 fps)
          - menu/hub → ~8s
          - HTTP 429 cooldown → skip until backoff expires (not process HOLD)
        """
        if not self.enabled or frame is None or getattr(frame, "size", 0) == 0:
            return
        if self.is_held():
            return
        if self._in_backoff():
            return
        try:
            from qoresence.graphs.look_gate import permit_confirm_look

            if not permit_confirm_look(reason=reason, force=force, has_frame=True):
                return
        except Exception:
            pass
        gst = (game_state or "").lower()
        crop = self._crop(
            frame, game_state=gst, game_profile=game_profile, game_title=game_title
        )
        has_scorebug = crop is not None and crop_misses_scorebug(crop) is None
        is_gameplay = gst in {"gameplay", "playing", "in_game", ""}
        if has_scorebug:
            # Misclassified menu with a live scorebug — use gameplay cadence, not menu-starved.
            is_gameplay = True
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

        from qoresence.vision.confirm_ticket import resolve_session_id

        source = dict(source_stamp or {})
        source["session_id"] = resolve_session_id()
        source["game_state"] = gst
        source["game_profile"] = game_profile
        source["submitted_ns"] = time.monotonic_ns()
        source_key = (source["session_id"], source.get("seq"), source.get("clock_ns"))
        now = time.time()
        soft_preempt = False
        with self._lock:
            if getattr(self, "recheck_enabled", False):
                if not source.get("seq") or not source.get("clock_ns"):
                    self._recheck_status = "missing_evidence"
                    return
                # force/score_changed remints may reuse the same seq stamp.
                if source_key == getattr(self, "_source_requested", None) and not (
                    force or reason in {"score_changed", "menu_exit", "first_lock"}
                ):
                    return
            if self._inflight and (now - self._inflight_since) > _INFLIGHT_WATCHDOG_S:
                log.info(
                    "scoreboard VLM watchdog: clearing stale inflight (%.1fs)",
                    now - self._inflight_since,
                )
                self._inflight = False

            priority = force or reason in {
                "score_changed",
                "menu_exit",
                "first_lock",
            }
            if self._inflight:
                inflight_age = (
                    (now - self._inflight_since) if self._inflight_since else 0.0
                )
                if priority and crop is not None:
                    # Do not drop score deltas while Quicksilver is on the wire.
                    # Queue latest full frame; _drain_pending_remint re-crops on clear.
                    self._pending_remint = {
                        "reason": reason if reason else "score_changed",
                        "force": True,
                        "game_state": gst,
                        "game_profile": game_profile,
                        "game_title": game_title,
                        "source_stamp": dict(source),
                        "frame": frame.copy(),
                    }
                    self._pending_remint_count += 1
                    log.info(
                        "scoreboard VLM pending remint (reason=%s inflight_age=%.1fs)",
                        reason,
                        inflight_age,
                    )
                elif (
                    has_scorebug
                    and crop is not None
                    and self._pending_remint is None
                ):
                    # Visible scorebug while a POST owns the slot — queue a
                    # remint and wait for that POST to finish. Do not
                    # soft-preempt: that abandons the waiter still holding
                    # Quicksilver and the next look never POSTs.
                    self._pending_remint = {
                        "reason": reason if reason else "tick",
                        "force": True,
                        "game_state": gst,
                        "game_profile": game_profile,
                        "game_title": game_title,
                        "source_stamp": dict(source),
                        "frame": frame.copy(),
                    }
                    self._pending_remint_count += 1
                    log.info(
                        "scoreboard VLM pending remint "
                        "(reason=%s inflight_age=%.1fs scorebug=1 wait_slot)",
                        reason or "tick",
                        inflight_age,
                    )
                    self._skip_inflight_count += 1
                    return
                # Soft preempt: force/score_changed remint waiting on a long POST.
                if (
                    self._pending_remint is not None
                    and inflight_age > _PENDING_REMINT_SOFT_BUDGET_S
                    and bool((self._pending_remint or {}).get("force"))
                    and str((self._pending_remint or {}).get("reason") or "")
                    in {"score_changed", "menu_exit", "first_lock"}
                ):
                    self._request_generation = (
                        getattr(self, "_request_generation", 0) + 1
                    )
                    self._inflight = False
                    soft_preempt = True
                    log.info(
                        "scoreboard VLM soft-preempt pending remint "
                        "(inflight_age=%.1fs budget=%.1fs)",
                        inflight_age,
                        _PENDING_REMINT_SOFT_BUDGET_S,
                    )
                elif priority and crop is not None:
                    return
                else:
                    self._skip_inflight_count += 1
                    log.info("scoreboard VLM skip: inflight")
                    return
            if soft_preempt:
                pass
            elif not force and (now - self._last_call) < interval:
                self._skip_interval_count += 1
                log.info(
                    "scoreboard VLM skip: interval (%.1fs < %.1fs)",
                    now - self._last_call,
                    interval,
                )
                return
            else:
                self._inflight = True
                self._inflight_since = now
                self._last_call = now
                self._last_reason = reason
                self._request_generation = getattr(self, "_request_generation", 0) + 1
                generation = self._request_generation
                self._source_requested = source_key
        if soft_preempt:
            self._drain_pending_remint()
            return
        if crop is None:
            with self._lock:
                self._inflight = False
            self._drain_pending_remint()
            return

        crop = crop.copy()

        def _run() -> None:
            try:
                source["analyzed_crop_hash"] = hashlib.sha256(crop.tobytes()).hexdigest()
                with _confirm_clock_heartbeat_while_inflight():
                    parsed = self._call_vlm(crop)
                with self._lock:
                    if generation != self._request_generation:
                        return
                    if source["session_id"] != resolve_session_id():
                        self._last = None
                        self._recheck_status = "session_changed"
                        return
                    http_status = self._last_http_status
                if parsed and all(
                    parsed.get(k) is None
                    for k in ("home_score", "away_score", "left_score", "right_score")
                ):
                    log.info("scoreboard VLM → empty board (reason=%s)", reason)
                    with self._lock:
                        # Don't sit 6s on a hollow-zero miss while the HUD is up.
                        self._last_call = time.time() - max(0.8, _GAMEPLAY_INTERVAL_S) + 1.5
                    parsed = None
                elif parsed is None and http_status == 200:
                    log.info("scoreboard VLM → empty HTTP 200 (reason=%s)", reason)
                    with self._lock:
                        self._last_call = time.time() - max(0.8, _GAMEPLAY_INTERVAL_S) + 1.5
                if parsed:
                    from qoresence.vision.board_why import vlm_last_grounded

                    if not vlm_last_grounded(parsed):
                        log.info(
                            "scoreboard VLM → ungrounded parse refused for remint "
                            "(scores=%s-%s paused=%s reason=%s)",
                            parsed.get("home_score"),
                            parsed.get("away_score"),
                            parsed.get("paused"),
                            reason,
                        )
                        with self._lock:
                            self._last_call = (
                                time.time() - max(0.8, _GAMEPLAY_INTERVAL_S) + 1.5
                            )
                        parsed = None
                if parsed:
                    parsed = dict(parsed)
                    parsed["_observation"] = dict(source)
                    rejected = False
                    prior_obs = None
                    candidate = None
                    with self._lock:
                        if generation != self._request_generation:
                            return
                        if getattr(self, "recheck_enabled", False):
                            from qoresence.vision.score_recheck import BoardObservation

                            hs, aws = parsed.get("home_score"), parsed.get("away_score")
                            if type(hs) is int and type(aws) is int:
                                prior_obs = self._score_recheck.accepted
                                candidate = BoardObservation(
                                    session_id=source["session_id"],
                                    frame_seq=int(source.get("seq") or 0),
                                    captured_ns=int(source.get("clock_ns") or 0),
                                    crop_hash=str(
                                        source.get("crop_hash")
                                        or source.get("analyzed_crop_hash")
                                        or ""
                                    ),
                                    home_team=str(
                                        parsed.get("home_team")
                                        or parsed.get("left_team")
                                        or ""
                                    ),
                                    away_team=str(
                                        parsed.get("away_team")
                                        or parsed.get("right_team")
                                        or ""
                                    ),
                                    home_score=hs,
                                    away_score=aws,
                                    scene=gst,
                                    quarter=parsed.get("quarter"),
                                    game_clock=parsed.get("clock"),
                                )
                                self._recheck_status = self._score_recheck.evaluate(
                                    candidate, time.monotonic_ns()
                                )
                            else:
                                # Grounded non-board read (visible_control, partial
                                # fields) — carry it; the mint path decides scores.
                                self._recheck_status = "no_board"
                            if self._recheck_status not in ("accepted", "no_board"):
                                self._last = None
                                rejected = True
                        if not rejected:
                            self._last = parsed
                            self._last_result_ts = time.time()
                            self._calls += 1
                            self._consecutive_timeouts = 0
                    # Advisory Jev verdict on changed same-identity
                    # transitions — recorded on the replay row, never
                    # consulted by the live mint path.
                    if (
                        prior_obs is not None
                        and candidate is not None
                        and candidate.identity == prior_obs.identity
                        and candidate.pair != prior_obs.pair
                        and self._recheck_status
                        in ("accepted", "recheck", "exhausted")
                    ):
                        from qoresence.observability.score_plausibility import (
                            transition_verdict,
                        )

                        verdict = transition_verdict(
                            prior_obs.pair,
                            candidate.pair,
                            warned_flag=self._jev_warned,
                        )
                        if verdict:
                            parsed["jev"] = verdict
                    _record_replay_row(parsed, self._recheck_status)
                    if rejected:
                        return
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
                    with self._lock:
                        # Slot-busy / empty 200 / parse fail: do not sit the
                        # full 6s gameplay interval. Retry in ~1.5s.
                        self._last_call = time.time() - max(0.8, _GAMEPLAY_INTERVAL_S) + 1.5
            except Exception as e:
                if self._is_read_timeout(e):
                    self._on_read_timeout()
                log.info("scoreboard VLM failed: %s (reason=%s)", e, reason)
            finally:
                drain = False
                with self._lock:
                    if generation == self._request_generation:
                        self._inflight = False
                        drain = True
                if drain:
                    self._drain_pending_remint()

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
    def _letterbox_for_vlm(crop_bgr: np.ndarray) -> np.ndarray:
        """Pad an ultra-wide scorebug so Gemini does not return empty HTTP 200.

        Live CFB strips (~768×115, aspect ~6.7) were readable to humans and
        crop_misses_scorebug, but Quicksilver json_object replies were empty.
        Detector still sees the raw strip; only the JPEG we POST is padded.
        """
        h, w = crop_bgr.shape[:2]
        if h < 8 or w < 8:
            return crop_bgr
        if (w / float(h)) <= 3.2:
            return crop_bgr
        target_h = max(h, int(round(w / 3.0)))
        pad = target_h - h
        top = pad // 2
        bot = pad - top
        return cv2.copyMakeBorder(
            crop_bgr,
            top,
            bot,
            0,
            0,
            cv2.BORDER_CONSTANT,
            value=(18, 42, 18),
        )

    @classmethod
    def _is_cfb_context(
        cls,
        game_profile: str | None = None,
        game_title: str | None = None,
        frame: np.ndarray | None = None,
    ) -> bool:
        """Detect CFB/college/NCAA from profile, title, or ticker/logo OCR."""
        from qoresence.vision.cfb_optical_markers import frame_has_cfb_optical_markers

        return frame_has_cfb_optical_markers(
            frame,
            game_profile=game_profile,
            game_title=game_title,
        )

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
        is_cfb = cls._is_cfb_context(game_profile, game_title, frame)
        if is_cfb:
            try:
                from qoresence.vision.cfb_optical_markers import set_football_confirm_hint

                set_football_confirm_hint("cfb_27", game_title)
            except Exception:
                pass

        effective_profile = game_profile
        if is_cfb and not is_madden:
            effective_profile = "cfb_27"
        elif is_cfb and is_madden:
            effective_profile = "cfb_27"

        if is_madden or is_cfb:
            fallback: np.ndarray | None = None
            fallback_refuse: str | None = None
            for frac in confirm_scorebug_bands(effective_profile):
                raw = cls._slice(frame, frac)
                if raw is None:
                    continue
                out = cls._prepare_crop(raw)
                miss = crop_misses_scorebug(out)
                if miss is None:
                    return out
                if fallback is None:
                    fallback = out
                    fallback_refuse = miss
            if fallback is None:
                return None
            # Fail-closed: player-CU / pause mid-frame must not ship as confirm crop.
            if fallback_refuse == "player_cu_crop":
                return None
            return fallback

        scorebug = primary_scorebug_crop(effective_profile)
        src = cls._slice(frame, _PAUSE_FRAC if menu else scorebug)
        if src is None:
            src = cls._slice(frame, scorebug if menu else _PAUSE_FRAC)
        if src is None:
            return None
        return cls._prepare_crop(src)

    def _call_vlm(self, crop_bgr: np.ndarray) -> dict[str, Any] | None:
        if self._in_backoff():
            return None
        refuse = crop_misses_scorebug(crop_bgr)
        kind = "scorebug" if refuse is None else str(refuse)
        try:
            self._last_crop_wh = (int(crop_bgr.shape[1]), int(crop_bgr.shape[0]))
        except Exception:
            self._last_crop_wh = None
        with self._lock:
            self._last_crop_refuse = refuse
            self._last_crop_kind = kind
        send = self._letterbox_for_vlm(crop_bgr)
        try:
            import pathlib

            logs_dir = pathlib.Path("logs")
            logs_dir.mkdir(exist_ok=True)
            cv2.imwrite(str(logs_dir / "vlm_last_crop.jpg"), crop_bgr)
            cv2.imwrite(str(logs_dir / "vlm_last_crop_vlm.jpg"), send)
        except Exception:
            pass
        ok, buf = cv2.imencode(".jpg", send, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
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
            "max_tokens": 2048,
            # gemini-3.5-flash-lite on Quicksilver accepts json_object; keeps shape strict.
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

            from qoresence.agents.quicksilver_slot import acquire_quicksilver

            with acquire_quicksilver(_QUICKSILVER_SLOT_WAIT_S) as got:
                if not got:
                    log.info("scoreboard VLM skip: Quicksilver slot busy")
                    return None
                r = requests.post(url, headers=headers, json=body, timeout=_HTTP_TIMEOUT_S)
            log.info("scoreboard VLM HTTP %d", r.status_code)
            with self._lock:
                self._last_http_status = r.status_code
            if r.status_code == 429 or r.status_code in _HOLD_HTTP:
                err_body = ""
                if r.status_code == 400:
                    try:
                        err_body = r.text
                    except Exception:
                        err_body = ""
                if self._on_terminal_http(r.status_code, body=err_body):
                    return None
            if r.status_code != 200:
                # Known HTTP from requests — do not urllib-retry (that was the storm).
                return None
            _refresh_confirm_clock_after_200()
            data = r.json()
        except Exception as e:
            if self._is_read_timeout(e):
                self._on_read_timeout()
                return None
            # stdlib fallback only when requests is missing or the socket failed (not timeout)
            import urllib.error
            import urllib.request

            req = urllib.request.Request(
                url,
                data=json.dumps(body).encode("utf-8"),
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:
                    code = resp.getcode()
                    log.info("scoreboard VLM HTTP %d", code)
                    if self._on_terminal_http(code):
                        return None
                    with self._lock:
                        self._last_http_status = code
                    raw = resp.read().decode("utf-8", errors="replace")
                if int(code) == 200:
                    _refresh_confirm_clock_after_200()
                data = json.loads(raw)
            except urllib.error.HTTPError as http_err:
                log.info("scoreboard VLM HTTP %d (error)", http_err.code)
                err_body = ""
                if http_err.code == 400:
                    try:
                        err_body = http_err.read().decode("utf-8", errors="replace")
                    except Exception:
                        err_body = ""
                if self._on_terminal_http(http_err.code, body=err_body):
                    return None
                with self._lock:
                    self._last_http_status = http_err.code
                log.warning("scoreboard VLM HTTP error: %s / %s", e, http_err)
                return None
            except Exception as e2:
                if self._is_read_timeout(e2):
                    self._on_read_timeout()
                    return None
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
        if finish == "length":
            log.info(
                "scoreboard VLM HTTP 200 finish=length — HOLD parse (truncated reply)"
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
        """Pick content vs reasoning by whichever field exposes the first `{`."""
        msg = choice.get("message") if isinstance(choice, dict) else None
        if not isinstance(msg, dict):
            msg = {}
        content = str(msg.get("content") or "").strip()
        reasoning = str(msg.get("reasoning_content") or "").strip()
        finish = str((choice or {}).get("finish_reason") or "")
        c_idx = content.find("{")
        r_idx = reasoning.find("{")
        if c_idx >= 0 and (r_idx < 0 or c_idx <= r_idx):
            return content, finish
        if r_idx >= 0:
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
        # Scene classifiers need the VLM's own pause read; ``paused`` is later
        # normalized for digit honesty (wordmarks → not paused).
        out["paused_raw"] = out["paused"]
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
        ScoreboardVlmReferee._fill_hollow_zero(out)
        from qoresence.vision.board_why import normalize_vlm_paused_flag

        return normalize_vlm_paused_flag(out) or out

    @staticmethod
    def _fill_hollow_zero(out: dict[str, Any]) -> None:
        """Wordmark + empty score slot is 0 (Madden hollow oval), not a dropped board."""
        lt, rt = out.get("left_team"), out.get("right_team")
        ls, rs = out.get("left_score"), out.get("right_score")
        if lt and rt:
            if ls is None and isinstance(rs, int):
                out["left_score"] = 0
                ls = 0
            if rs is None and isinstance(ls, int):
                out["right_score"] = 0
                rs = 0
        hs, aws = out.get("home_score"), out.get("away_score")
        if hs is None and aws is None and isinstance(ls, int) and isinstance(rs, int):
            hl = out.get("home_left")
            if hl is True:
                out["home_score"], out["away_score"] = ls, rs
            else:
                # Madden HUD: home is usually the right mark.
                out["home_score"], out["away_score"] = rs, ls
                if hl is None:
                    out["home_left"] = False


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
