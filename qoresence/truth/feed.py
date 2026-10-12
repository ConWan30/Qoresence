"""Truth feed — locked score facts from ``visual_context``, hash-chained to JSONL.

Default OFF. Enable with ``--truth-feed`` or ``QORESENCE_TRUTH_FEED=1``.
See docs/TRUTH_FEED.md and docs/VERIFIED_REEL_PLAN.md (fail-closed rules).

Fail-closed rules (a fact is written only when ALL hold):

* ``visual_context`` with ``score_vlm_locked`` true **and** a ``confirm_ticket_id``.
* The ConfirmTicket dict is on the payload (``details.confirm_ticket``), agrees
  with the payload digits and ticket id, and ``ticket_is_licensed_lock`` passes
  (non-empty crop hash, not 0-0, observed within the digit max age).
* Capture is live (FrameHub has a fresh frame), like the OBS bridge (PR #280).
* The locked pair differs from the previous locked pair (holds are deduped).
  First lock = ``score_lock`` (baseline); an increase = ``score_change``; a
  decrease / reset = ``score_lock`` with ``meta.baseline_reset`` (never a change).

Unlocked, blank, held, stale or disagreeing boards produce nothing.

Controller corroboration is shallow: PLAY-domain InputRing edges in the window
before the lock. With enough presses the level is ``screen+input`` and the label
``verified``; otherwise ``screen_only`` / ``unverified`` (reel plan §5/§7).
OBSERVE-domain input never corroborates.

Threading (AGENTS.md rules 1/4/5): the bus subscriber only copies a few fields
into a bounded drop-oldest deque and sets an Event. Parsing, InputRing reads,
hashing, signing and disk I/O run on the feed's own daemon worker. The feed
never emits bus events and never takes a lobe lock.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qoresence.truth.chain import TruthChainWriter, verify_file
from qoresence.truth.model import (
    LABEL_META,
    LABEL_UNVERIFIED,
    LABEL_VERIFIED,
    LEVEL_SCREEN_INPUT,
    LEVEL_SCREEN_ONLY,
    TruthFact,
)
from qoresence.truth.signing import Signer, default_key_path, load_or_create_signer

log = logging.getLogger(__name__)

_LOCAL_READERS = {"local_scorebug"}
_CLOUD_READERS = {"gemini", "quicksilver", "deepseek"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.getenv(name)
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


@dataclass(frozen=True)
class TruthFeedConfig:
    enabled: bool = False
    out_dir: str = "logs/truth"
    key_path: str = ""  # "" = ~/.qoresence/truth_key (or QORESENCE_TRUTH_KEY)
    sign: bool = True  # False = unsigned hash chain even if cryptography exists
    input_window_s: float = 15.0
    min_play_presses: int = 2
    stale_capture_s: float = 5.0
    require_live_capture: bool = True
    clip_link_window_s: float = 60.0
    queue_max: int = 256

    @classmethod
    def from_env(cls, *, enabled: bool | None = None, **overrides: Any) -> TruthFeedConfig:
        base: dict[str, Any] = {
            "enabled": _env_bool("QORESENCE_TRUTH_FEED", False) if enabled is None else enabled,
            "out_dir": os.getenv("QORESENCE_TRUTH_DIR") or "logs/truth",
            "sign": _env_bool("QORESENCE_TRUTH_SIGN", True),
            "input_window_s": _env_float("QORESENCE_TRUTH_INPUT_WINDOW_S", 15.0),
        }
        base.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**base)

    def public_dict(self) -> dict[str, Any]:
        return {
            "out_dir": self.out_dir,
            "sign": self.sign,
            "input_window_s": self.input_window_s,
            "min_play_presses": self.min_play_presses,
            "require_live_capture": self.require_live_capture,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Parsing (pure; tests drive these directly)
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LockCandidate:
    """Fields copied off a ``visual_context`` event on the bus thread."""

    session_id: str
    clock_ns: int
    payload: dict[str, Any]


def _int_or_none(v: Any) -> int | None:
    try:
        if v is None or isinstance(v, bool):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def _default_licensed(ticket: dict[str, Any]) -> bool:
    from qoresence.vision.confirm_ticket import ConfirmTicket, ticket_is_licensed_lock

    names = {f.name for f in fields(ConfirmTicket)}
    t = ConfirmTicket(**{k: v for k, v in ticket.items() if k in names})
    return bool(ticket_is_licensed_lock(t))


def reader_plane(reader: str) -> str:
    r = (reader or "").lower()
    if r in _LOCAL_READERS:
        return "local"
    if r in _CLOUD_READERS:
        return "cloud"
    return "unknown"


def parse_locked_score(
    payload: dict[str, Any] | None,
    *,
    licensed: Callable[[dict[str, Any]], bool] = _default_licensed,
) -> tuple[dict[str, Any] | None, str]:
    """Fail-closed parse. Returns ``(lock, "ok")`` or ``(None, reason)``."""
    p = payload if isinstance(payload, dict) else {}
    if not bool(p.get("score_vlm_locked")):
        return None, "not_locked"
    tid = str(p.get("confirm_ticket_id") or "").strip()
    if not tid:
        return None, "no_ticket_id"
    fb = p.get("football")
    if not isinstance(fb, dict):
        return None, "no_board"
    home = _int_or_none(fb.get("home_score"))
    away = _int_or_none(fb.get("away_score"))
    if home is None or away is None:
        return None, "blank_board"
    if not (0 <= home <= 199 and 0 <= away <= 199):
        return None, "out_of_range"
    details = p.get("details") if isinstance(p.get("details"), dict) else {}
    ticket = details.get("confirm_ticket")
    if not isinstance(ticket, dict):
        return None, "no_ticket"
    if str(ticket.get("ticket_id") or "") != tid:
        return None, "ticket_id_mismatch"
    if (
        _int_or_none(ticket.get("home_score")) != home
        or _int_or_none(ticket.get("away_score")) != away
    ):
        return None, "ticket_digits_mismatch"
    try:
        if not licensed(ticket):
            return None, "ticket_not_licensed"
    except Exception:
        return None, "ticket_check_failed"
    reader = str(ticket.get("source") or "")
    crop_hash = str(ticket.get("observed_crop_hash") or ticket.get("crop_hash") or "")
    frame_seq = ticket.get("observed_frame_seq")
    if frame_seq is None:
        frame_seq = ticket.get("frame_seq")
    t_lock = _int_or_none(ticket.get("observed_clock_ns")) or _int_or_none(ticket.get("clock_ns"))
    return {
        "pair": (home, away),
        "scores": {
            "home": home,
            "away": away,
            "home_team": fb.get("home_team") or fb.get("home_team_raw") or None,
            "away_team": fb.get("away_team") or fb.get("away_team_raw") or None,
            "home_left": fb.get("home_left"),
            "quarter": _int_or_none(fb.get("quarter")),
        },
        "frame": {
            "frame_hash": str(p.get("frame_hash") or "") or None,
            "lock_crop_hash": crop_hash or None,
            "frame_seq": _int_or_none(frame_seq),
            "hash_note": "frame_hash=analyzed frame carrying the lock; "
            "lock_crop_hash=scorebug crop that minted the ticket",
        },
        "source": {
            "reader": reader or "unknown",
            "plane": reader_plane(reader),
            "model": str(ticket.get("model") or p.get("model") or "") or None,
            "ticket_id": tid,
        },
        "game_profile": str(p.get("game_profile") or "") or None,
        "t_lock_ns": t_lock,
    }, "ok"


def corroborate_input(
    events: list[Any] | None,
    *,
    t_lock_ns: int,
    window_s: float,
    min_presses: int,
) -> tuple[dict[str, Any] | None, str, list[str]]:
    """Shallow PLAY-domain input presence check. Returns (summary, level, reasons)."""
    if events is None:
        return None, LEVEL_SCREEN_ONLY, ["input_ring_unavailable"]
    play = []
    observe = 0
    for e in events:
        dom = getattr(e, "hid_domain", None)
        if dom is None and isinstance(e, dict):
            dom = e.get("hid_domain")
        if dom == "play":
            play.append(e)
        else:
            observe += 1

    def _f(e: Any, k: str) -> Any:
        return e.get(k) if isinstance(e, dict) else getattr(e, k, None)

    presses = [e for e in play if _f(e, "kind") in ("press", "trigger")]
    if not play:
        reasons = ["observe_domain_only"] if observe else ["no_play_input_in_window"]
        if observe == 0:
            return None, LEVEL_SCREEN_ONLY, reasons
        return (
            {
                "domain": "play",
                "window_s": window_s,
                "play_events": 0,
                "play_presses": 0,
                "other_domain_events": observe,
            },
            LEVEL_SCREEN_ONLY,
            reasons,
        )
    last_ns = max(int(_f(e, "clock_ns") or 0) for e in play)
    summary = {
        "domain": "play",
        "window_s": window_s,
        "play_events": len(play),
        "play_presses": len(presses),
        "other_domain_events": observe,
        "last_input_to_lock_s": round(max(0, t_lock_ns - last_ns) / 1e9, 3),
        "trace_sha256": hashlib.sha256(
            repr(
                sorted(
                    (int(_f(e, "clock_ns") or 0), str(_f(e, "kind")), str(_f(e, "name")))
                    for e in play
                )
            ).encode("utf-8")
        ).hexdigest(),
        "depth": "presence_only",
    }
    if len(presses) >= max(1, int(min_presses)):
        return summary, LEVEL_SCREEN_INPUT, []
    return summary, LEVEL_SCREEN_ONLY, ["too_few_play_presses"]


def _default_frame_stamp() -> dict[str, Any]:
    from qoresence.monitor.frame_hub import get_latest_stamp

    return get_latest_stamp()


def _default_input_window(t0_ns: int, t1_ns: int) -> list[Any] | None:
    try:
        from qoresence.sync.input_ring import get_input_ring

        return get_input_ring().in_window(t0_ns, t1_ns)
    except Exception:
        return None


def _wall_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _safe_session(session_id: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(session_id or ""))
    return keep[:96] or "session"


# ──────────────────────────────────────────────────────────────────────────────
# Feed
# ──────────────────────────────────────────────────────────────────────────────


class TruthFeed:
    def __init__(
        self,
        config: TruthFeedConfig,
        *,
        session_id: str,
        signer: Signer | None = None,
        sign_reason: str = "disabled",
        frame_stamp: Callable[[], dict[str, Any]] | None = None,
        input_window: Callable[[int, int], list[Any] | None] | None = None,
        licensed: Callable[[dict[str, Any]], bool] | None = None,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.config = config
        self.session_id = str(session_id or "session")
        self.signer = signer
        self.sign_reason = sign_reason if signer is None else "ok"
        self._frame_stamp = frame_stamp or _default_frame_stamp
        self._input_window = input_window or _default_input_window
        self._licensed = licensed or _default_licensed
        self._clock_ns = clock_ns
        self.path = self._pick_path(Path(config.out_dir), _safe_session(self.session_id))
        self.writer = TruthChainWriter(self.path, signer=signer)

        # Mailbox (bus thread → worker). Private lock, held only for deque ops.
        self._mail_lock = threading.Lock()
        self._mail: deque[tuple[str, Any]] = deque(maxlen=max(8, int(config.queue_max)))
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._new_fact = threading.Condition()

        # Worker-owned state
        self._last_pair: tuple[int, int] | None = None
        self._last_score_seq: int | None = None
        self._last_score_ns: int | None = None

        # Stats
        self.events_seen = 0
        self.dropped = 0
        self.facts = 0
        self.refused: dict[str, int] = {}
        self.started = False

    def _pick_path(self, out_dir: Path, stem: str) -> Path:
        """Resume the session file only if it was written with the same key mode."""
        from qoresence.truth.chain import last_record

        want_key = self.signer.key_id if self.signer is not None else None
        n = 1
        while True:
            p = out_dir / (f"truth_{stem}.jsonl" if n == 1 else f"truth_{stem}_{n}.jsonl")
            last = last_record(p) if p.exists() else None
            if last is None or last.get("key_id") == want_key:
                return p
            n += 1

    # ── bus side (enqueue only) ───────────────────────────────────────────────

    def on_event(self, event: Any) -> None:
        """Bus subscriber. Copies a reference into the mailbox; never blocks on I/O."""
        try:
            et = getattr(event, "type", None)
            if getattr(et, "value", et) != "visual_context":
                return
            payload = getattr(event, "payload", None)
            if not isinstance(payload, dict) or not payload.get("score_vlm_locked"):
                return  # unlocked: nothing to say (fail-closed)
            # Shallow snapshot of the few fields we read (later subscribers may
            # mutate the shared payload). No parsing here.
            details = payload.get("details")
            ticket = details.get("confirm_ticket") if isinstance(details, dict) else None
            fb = payload.get("football")
            snap = {
                "score_vlm_locked": True,
                "confirm_ticket_id": payload.get("confirm_ticket_id"),
                "football": dict(fb) if isinstance(fb, dict) else None,
                "details": {"confirm_ticket": dict(ticket) if isinstance(ticket, dict) else None},
                "frame_hash": payload.get("frame_hash"),
                "model": payload.get("model"),
                "game_profile": payload.get("game_profile"),
            }
            cand = LockCandidate(
                session_id=str(getattr(event, "session_id", "") or ""),
                clock_ns=int(getattr(event, "clock_ns", 0) or 0),
                payload=snap,
            )
        except Exception:
            return
        self._enqueue("lock", cand)

    def note_clip(self, info: dict[str, Any]) -> None:
        self._enqueue("clip", dict(info))

    def _enqueue(self, kind: str, item: Any) -> None:
        with self._mail_lock:
            if len(self._mail) == self._mail.maxlen:
                self.dropped += 1
            self._mail.append((kind, item))
            self.events_seen += 1
        self._wake.set()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, bus: Any = None) -> None:
        if self.started:
            return
        self.started = True
        self._append(
            TruthFact(
                kind="session_start",
                session_id=self.session_id,
                clock_ns=self._clock_ns(),
                wall_utc=_wall_utc(),
                verification={"level": None, "label": LABEL_META, "reasons": []},
                meta={
                    "pubkey": self.signer.pubkey_hex if self.signer else None,
                    "sign_reason": self.sign_reason,
                    "honesty": "scores only from licensed ConfirmTicket locks; "
                    "uncorroborated facts are labelled unverified",
                },
            )
        )
        if bus is not None and self._unsubscribe is None:
            self._unsubscribe = bus.subscribe(self.on_event)
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="truth-feed", daemon=True)
            self._thread.start()
        log.info(
            "Truth feed enabled → %s (signed=%s%s)",
            self.path,
            self.signer is not None,
            "" if self.signer else f", {self.sign_reason}",
        )

    def stop(self) -> None:
        if self._unsubscribe is not None:
            try:
                self._unsubscribe()
            except Exception:
                pass
            self._unsubscribe = None
        self._stop.set()
        self._wake.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=2.0)
        self._thread = None
        if self.started:
            try:
                self.step()  # drain what is left
            except Exception:
                pass
            self._append(
                TruthFact(
                    kind="session_end",
                    session_id=self.session_id,
                    clock_ns=self._clock_ns(),
                    wall_utc=_wall_utc(),
                    verification={"level": None, "label": LABEL_META, "reasons": []},
                    meta={"facts": self.facts, "refused": dict(self.refused)},
                )
            )
            self.started = False
        self.writer.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=0.5)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.step()
            except Exception as e:  # never kill the worker
                log.debug("truth feed step error: %s", type(e).__name__)

    # ── core (synchronous; tests drive this directly) ────────────────────────

    def step(self) -> int:
        """Drain the mailbox. Returns the number of facts written."""
        with self._mail_lock:
            items = list(self._mail)
            self._mail.clear()
        n = 0
        for kind, item in items:
            try:
                rec = self._handle_lock(item) if kind == "lock" else self._handle_clip(item)
            except Exception as e:
                self._refuse(f"error:{type(e).__name__}")
                rec = None
            if rec is not None:
                n += 1
        return n

    def _refuse(self, reason: str) -> None:
        self.refused[reason] = self.refused.get(reason, 0) + 1

    def _capture_live(self) -> bool:
        if not self.config.require_live_capture:
            return True
        try:
            st = self._frame_stamp() or {}
        except Exception:
            return False
        if not st.get("has_frame"):
            return False
        try:
            age = st.get("age_s")
            return age is not None and float(age) <= float(self.config.stale_capture_s)
        except (TypeError, ValueError):
            return False

    def _handle_lock(self, cand: LockCandidate) -> dict[str, Any] | None:
        lock, why = parse_locked_score(cand.payload, licensed=self._licensed)
        if lock is None:
            self._refuse(why)
            return None
        pair = lock["pair"]
        if pair == self._last_pair:
            return None  # held lock: same fact, no new line
        if not self._capture_live():
            self._refuse("capture_not_live")
            return None
        prev = self._last_pair
        meta: dict[str, Any] = {}
        if prev is None:
            kind = "score_lock"
        elif pair[0] >= prev[0] and pair[1] >= prev[1]:
            kind = "score_change"
        else:
            kind = "score_lock"
            meta["baseline_reset"] = True
        t_lock = int(lock.get("t_lock_ns") or cand.clock_ns or self._clock_ns())
        w_ns = int(float(self.config.input_window_s) * 1e9)
        try:
            evs = self._input_window(t_lock - w_ns, t_lock)
        except Exception:
            evs = None
        controller, level, reasons = corroborate_input(
            evs,
            t_lock_ns=t_lock,
            window_s=float(self.config.input_window_s),
            min_presses=int(self.config.min_play_presses),
        )
        label = LABEL_VERIFIED if level == LEVEL_SCREEN_INPUT else LABEL_UNVERIFIED
        fact = TruthFact(
            kind=kind,
            session_id=self.session_id,
            clock_ns=t_lock,
            wall_utc=_wall_utc(),
            game_profile=lock["game_profile"],
            scores=lock["scores"],
            prev_scores=({"home": prev[0], "away": prev[1]} if prev is not None else None),
            frame=lock["frame"],
            source={**lock["source"], "bus_session_id": cand.session_id or None},
            controller=controller,
            verification={"level": level, "label": label, "reasons": reasons},
            meta=meta or None,
        )
        rec = self._append(fact)
        if rec is None:
            return None
        self._last_pair = pair
        self._last_score_seq = int(rec["seq"])
        self._last_score_ns = t_lock
        return rec

    def _handle_clip(self, info: dict[str, Any]) -> dict[str, Any] | None:
        path = Path(str(info.get("path") or ""))
        if not path.is_file():
            self._refuse("clip_missing")
            return None
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        now = int(info.get("clock_ns") or self._clock_ns())
        related = None
        if (
            self._last_score_seq is not None
            and self._last_score_ns is not None
            and 0 <= now - self._last_score_ns <= int(self.config.clip_link_window_s * 1e9)
        ):
            related = self._last_score_seq
        fact = TruthFact(
            kind="clip_ref",
            session_id=self.session_id,
            clock_ns=now,
            wall_utc=_wall_utc(),
            clip={
                "file": path.name,
                "sha256": h.hexdigest(),
                "size_bytes": path.stat().st_size,
                "duration_s": info.get("duration_s"),
                "source": info.get("source") or "foundry_ring",
                "near_score_seq": related,
            },
            verification={
                "level": None,
                "label": LABEL_UNVERIFIED,
                "reasons": ["clip_link_is_temporal_only"],
            },
        )
        return self._append(fact)

    def _append(self, fact: TruthFact) -> dict[str, Any] | None:
        rec = self.writer.append(fact)
        if rec is None:
            self._refuse("sign_failed")
            return None
        if fact.kind != "session_start" and fact.kind != "session_end":
            self.facts += 1
        with self._new_fact:
            self._new_fact.notify_all()
        return rec

    # ── read side (deck) ──────────────────────────────────────────────────────

    def recent(self, since: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return self.writer.recent(since=since, limit=limit)

    def wait_for_new(self, timeout_s: float) -> None:
        with self._new_fact:
            self._new_fact.wait(timeout=max(0.0, float(timeout_s)))

    def verify(self) -> dict[str, Any]:
        out = verify_file(self.path, pubkey_hex=self.signer.pubkey_hex if self.signer else None)
        out["path"] = str(self.path)
        return out

    def stats(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "path": str(self.path),
            "signed": self.signer is not None,
            "sign_reason": self.sign_reason,
            "key_id": self.signer.key_id if self.signer else None,
            "facts": int(self.facts),
            "next_seq": int(self.writer.next_seq),
            "events_seen": int(self.events_seen),
            "dropped": int(self.dropped),
            "refused": dict(self.refused),
            "config": self.config.public_dict(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Process-wide handle (deck + clip hook)
# ──────────────────────────────────────────────────────────────────────────────

_FEED: TruthFeed | None = None


def get_truth_feed() -> TruthFeed | None:
    return _FEED


def attach_health(body: dict[str, Any]) -> None:
    """Add ``truth_feed`` to a /health body — only when the feed is enabled."""
    f = _FEED
    if f is not None:
        body["truth_feed"] = f.stats()


def note_clip_exported(
    path: str | Path, *, duration_s: float | None = None, source: str = "foundry_ring"
) -> None:
    """Clip export hook: enqueue only (hash computed on the feed worker). No-op when off."""
    f = _FEED
    if f is None:
        return
    try:
        f.note_clip(
            {
                "path": str(path),
                "duration_s": round(float(duration_s), 3) if duration_s else None,
                "source": source,
                "clock_ns": time.monotonic_ns(),
            }
        )
    except Exception:
        pass


def make_truth_feed_from_config(
    config: TruthFeedConfig | None, *, bus: Any = None, session_id: str | None = None
) -> TruthFeed | None:
    """Start the feed when enabled; ``None`` otherwise (no key, no files)."""
    global _FEED
    if config is None or not config.enabled:
        return None
    if _FEED is not None:
        _FEED.stop()
    signer, reason = (None, "disabled")
    if config.sign:
        signer, reason = load_or_create_signer(
            Path(config.key_path).expanduser() if config.key_path else default_key_path()
        )
    sid = session_id or str(getattr(bus, "session_id", "") or "session")
    feed = TruthFeed(config, session_id=sid, signer=signer, sign_reason=reason)
    feed.start(bus)
    _FEED = feed
    return feed


def stop_truth_feed() -> None:
    global _FEED
    f, _FEED = _FEED, None
    if f is not None:
        f.stop()
