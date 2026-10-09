"""Extractor-facing service: flag, sampling, agreement, cross-check, health.

Runs inline on the scoreboard lock worker (``FootballScoreboardExtractor``),
never on the capture/HID/bus threads. A read costs well under a millisecond,
and reads are rate-limited to the agreement sampling interval anyway. No bus
events are emitted and no lobe locks are taken here.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import numpy as np

from qoresence.sync.digit_integrity import CONFIRM_DIGIT_MAX_AGE_NS
from qoresence.vision.local_scorebug.agreement import AgreementConfig, AgreementWindow
from qoresence.vision.local_scorebug.reader import FrameRead, ScorebugReader

log = logging.getLogger(__name__)

LOCAL_SOURCE = "local_scorebug"
ENV_FLAG = "QORESENCE_LOCAL_SCOREBUG"
_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off"}


def local_scorebug_flag() -> str:
    """'forced_on', 'forced_off' or 'default' (env QORESENCE_LOCAL_SCOREBUG)."""
    raw = os.environ.get(ENV_FLAG, "").strip().lower()
    if raw in _ON:
        return "forced_on"
    if raw in _OFF:
        return "forced_off"
    return "default"


def local_scorebug_enabled() -> bool:
    """On unless QORESENCE_LOCAL_SCOREBUG=0.

    Default ON with or without a cloud scorebug key. With no key it is the only
    seeing path for Madden. With a key, local reads may lock and the cloud read
    acts as a cross-check (see ``choose_board``).
    """
    return local_scorebug_flag() != "forced_off"


def cloud_scorebug_active() -> bool:
    try:
        from qoresence.vision.scoreboard_vlm import get_scoreboard_vlm

        return bool(get_scoreboard_vlm().enabled)
    except Exception:
        return False


def _pair_of(board: dict[str, Any] | None) -> tuple[Any, Any] | None:
    if not board:
        return None
    ls, rs = board.get("left_score"), board.get("right_score")
    if ls is not None and rs is not None:
        return ("lr", (int(ls), int(rs)))
    hs, aw = board.get("home_score"), board.get("away_score")
    if hs is not None and aw is not None:
        return ("ha", (int(hs), int(aw)))
    return None


def choose_board(
    local: dict[str, Any] | None,
    cloud: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    """Pick the board the mint path sees this tick, and say why.

    * no local sure board        -> cloud board unchanged (today's behaviour)
    * local sure, no cloud board -> local (keyless path, stricter gates)
    * both, cloud read is older than the local pair -> local (cloud saw an
      earlier screen and cannot contradict it)
    * both, same pair            -> local (evidence-bound to the read frame)
    * both, different pair       -> nothing: blank until they agree
    """
    if local is None:
        return cloud, "cloud" if cloud else "none"
    cp = _pair_of(cloud)
    if cp is None:
        return local, "local"
    obs = (cloud or {}).get("_observation") or {}
    try:
        cloud_ns = int(obs.get("clock_ns") or 0)
    except (TypeError, ValueError):
        cloud_ns = 0
    pair_since = int(((local.get("local") or {}).get("pair_since_ns")) or 0)
    if cloud_ns and pair_since and cloud_ns < pair_since:
        return local, "local_newer_than_cloud"
    kind, pair = cp
    lp = (
        (local.get("left_score"), local.get("right_score"))
        if kind == "lr"
        else (local.get("home_score"), local.get("away_score"))
    )
    if tuple(lp) == tuple(pair):
        return local, "local_cloud_agree"
    return None, "cross_check_disagree"


class LocalScorebugService:
    def __init__(
        self,
        reader: ScorebugReader | None = None,
        config: AgreementConfig | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._reader = reader
        self._reader_error = ""
        self._window = AgreementWindow(config)
        self._last_sample_ns = 0
        self._last_seq: Any = None
        self._last_read: FrameRead | None = None
        self._sure: dict[str, Any] | None = None
        self._pair_seen: tuple[int, int] | None = None
        self._pair_since_ns = 0
        self._reads = 0
        self._agreed = 0
        self._last_reason = "idle"
        self._last_choice = ""
        self._disagree = 0

    # ---- reader -------------------------------------------------------------
    def reader(self) -> ScorebugReader | None:
        if self._reader is None and not self._reader_error:
            try:
                self._reader = ScorebugReader()
            except Exception as e:  # missing/corrupt pack -> stay blank forever
                self._reader_error = f"{type(e).__name__}: {e}"
                log.warning("local scorebug reader unavailable: %s", self._reader_error)
        return self._reader

    # ---- main entry ---------------------------------------------------------
    def observe(
        self,
        frame: np.ndarray | None,
        *,
        stamp: dict[str, Any] | None = None,
        session_id: str = "",
        game_state: str = "",
        game_profile: str | None = None,
        home_left: bool = False,
        now_ns: int | None = None,
    ) -> dict[str, Any] | None:
        """Read one frame (rate-limited) and return the current sure board or None."""
        rd = self.reader()
        if rd is None or frame is None or getattr(frame, "size", 0) == 0:
            return None
        st = dict(stamp or {})
        now = int(now_ns or time.monotonic_ns())
        clock_ns = int(st.get("clock_ns") or 0) or now
        seq = st.get("seq")
        with self._lock:
            cfg = self._window.config
            same_frame = seq is not None and seq == self._last_seq
            if same_frame or (
                self._last_sample_ns and 0 <= clock_ns - self._last_sample_ns < cfg.min_interval_ns
            ):
                # Not new evidence (same FrameHub frame, or too soon): no new read.
                return self._current_locked(now, session_id)
            self._last_sample_ns = clock_ns
            self._last_seq = seq
        read = rd.read(frame)
        crop_hash = str(st.get("crop_hash") or "")
        if not crop_hash:
            try:
                from qoresence.vision.scorebug_crops import scorebug_crop_hash

                crop_hash = str(scorebug_crop_hash(frame) or "")
            except Exception:
                crop_hash = ""
        with self._lock:
            self._reads += 1
            self._last_read = read
            if read.ok and read.pair is not None:
                if read.pair != self._pair_seen:
                    self._pair_seen = read.pair
                    self._pair_since_ns = clock_ns
            res = self._window.offer(
                read, clock_ns=clock_ns, crop_hash=crop_hash, session_id=session_id
            )
            self._last_reason = res.reason
            if not res.agreed or res.read is None:
                self._sure = None
                return None
            self._agreed += 1
            r = res.read
            left, right = int(r.left_score or 0), int(r.right_score or 0)
            home, away = (left, right) if home_left else (right, left)
            self._sure = {
                "left_score": left,
                "right_score": right,
                "home_score": home,
                "away_score": away,
                "home_left": bool(home_left),
                "quarter": r.quarter,
                "clock_seconds": r.clock_seconds,
                "clock": r.clock_text,
                "paused": False,
                "_source": LOCAL_SOURCE,
                "_model": rd.model_id,
                "_observation": {
                    "seq": st.get("seq"),
                    "clock_ns": res.last_ns,
                    "crop_hash": res.crop_hash,
                    "session_id": session_id,
                    "game_state": game_state,
                    "game_profile": game_profile,
                },
                "local": {
                    "profile": r.profile_id,
                    "layout_version": rd.profile.layout_version,
                    "agree_n": res.run,
                    "agree_first_ns": res.first_ns,
                    "suspicious_recheck": res.suspicious,
                    "pair_since_ns": self._pair_since_ns,
                    "score_conf": r.score_conf,
                    "score_margin": r.score_margin,
                    "clock_conf": r.clock_conf,
                    "quarter_conf": r.quarter_conf,
                },
            }
            return dict(self._sure)

    def _current_locked(self, now_ns: int, session_id: str) -> dict[str, Any] | None:
        """The last agreed board, if same session and its frame is under 8 s old."""
        sure = self._sure
        if sure is None:
            return None
        obs = sure.get("_observation") or {}
        if obs.get("session_id") != session_id:
            return None
        if not 0 <= now_ns - int(obs.get("clock_ns") or 0) <= CONFIRM_DIGIT_MAX_AGE_NS:
            return None
        return dict(sure)

    def note_choice(self, why: str) -> None:
        with self._lock:
            self._last_choice = why
            if why == "cross_check_disagree":
                self._disagree += 1

    def stats(self) -> dict[str, Any]:
        with self._lock:
            rd = self._reader
            last = self._last_read
            return {
                "enabled": local_scorebug_enabled(),
                "flag": local_scorebug_flag(),
                "cloud_cross_check": cloud_scorebug_active(),
                "profile": rd.profile.profile_id if rd else None,
                "model": rd.model_id if rd else None,
                "reader_error": self._reader_error or None,
                "reads": self._reads,
                "agreed": self._agreed,
                "state": "sure" if self._sure else "blank",
                "reason": self._last_reason,
                "last_frame_reason": last.reason if last else None,
                "last_choice": self._last_choice or None,
                "cross_check_disagree": self._disagree,
            }


_SERVICE: LocalScorebugService | None = None
_SERVICE_LOCK = threading.Lock()


def get_local_scorebug() -> LocalScorebugService:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            _SERVICE = LocalScorebugService()
        return _SERVICE


def reset_local_scorebug(service: LocalScorebugService | None = None) -> None:
    """Tests: drop the singleton (or install a prepared one)."""
    global _SERVICE
    with _SERVICE_LOCK:
        _SERVICE = service
