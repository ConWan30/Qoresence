"""OBS bridge spike — drive OBS from locked scorebug events via obs-websocket v5.

Default OFF. Enabled with ``--obs`` (or ``QORESENCE_OBS=1``). See docs/OBS_BRIDGE.md.

Honesty / fail-closed rules:

* The only input is the ``visual_context`` bus event. A score is shown only when
  ``score_vlm_locked`` is true (ConfirmTicket minted) **and** the capture is live
  (FrameHub has a fresh frame). Anything else blanks the OBS text source.
* Replay saves / scene flashes / chapter markers fire only on a genuine locked
  score *increase* versus the previous locked score. The first lock of a session
  is a baseline (no replay); a locked decrease (new game / correction) only
  updates the text. Replay saves are rate-limited.

Threading (AGENTS.md rules 1/4/5): the bus subscriber only copies a few fields
into a single-slot mailbox and sets an Event. All OBS network I/O happens on the
bridge's own daemon worker. The bridge never emits bus events and never takes a
lobe lock.

The password comes from ``QORESENCE_OBS_PASSWORD`` only. It is never logged,
never put in ``/health`` and never in an error string (obsws-python logs it at
INFO on connect, so its logger is silenced).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

DEFAULT_TEXT_SOURCE = "Qoresence Score"
_BACKOFF_START_S = 1.0
_BACKOFF_MAX_S = 30.0


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────


def _env_float(name: str, default: float) -> float:
    try:
        raw = os.getenv(name)
        return float(raw) if raw not in (None, "") else default
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ObsBridgeConfig:
    enabled: bool = False
    host: str = "localhost"
    port: int = 4455
    password: str = field(default="", repr=False)
    text_source: str = DEFAULT_TEXT_SOURCE
    # Empty scene name = no scene flash.
    scene: str = ""
    scene_hold_s: float = 4.0
    replay: bool = True
    replay_min_interval_s: float = 20.0
    chapters: bool = False
    # Capture is "live" only if FrameHub's latest frame is younger than this.
    stale_capture_s: float = 5.0
    connect_timeout_s: float = 3.0

    @classmethod
    def from_env(cls, *, enabled: bool = False, **overrides: Any) -> ObsBridgeConfig:
        """Build from env; non-None ``overrides`` (CLI flags) win. Password is env-only."""
        try:
            port = int(os.getenv("QORESENCE_OBS_PORT") or 4455)
        except ValueError:
            port = 4455
        base: dict[str, Any] = {
            "enabled": bool(enabled) or _env_bool("QORESENCE_OBS", False),
            "host": os.getenv("QORESENCE_OBS_HOST") or "localhost",
            "port": port,
            "password": os.getenv("QORESENCE_OBS_PASSWORD") or "",
            "text_source": os.getenv("QORESENCE_OBS_TEXT_SOURCE") or DEFAULT_TEXT_SOURCE,
            "scene": os.getenv("QORESENCE_OBS_SCENE") or "",
            "scene_hold_s": _env_float("QORESENCE_OBS_SCENE_HOLD_S", 4.0),
            "replay": _env_bool("QORESENCE_OBS_REPLAY", True),
            "replay_min_interval_s": _env_float("QORESENCE_OBS_REPLAY_MIN_INTERVAL_S", 20.0),
            "chapters": _env_bool("QORESENCE_OBS_CHAPTERS", False),
        }
        overrides.pop("password", None)  # env only — never from argv
        base.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**base)

    def public_dict(self) -> dict[str, Any]:
        """Config safe for /health (no password)."""
        return {
            "host": self.host,
            "port": self.port,
            "password_set": bool(self.password),
            "text_source": self.text_source,
            "scene": self.scene,
            "scene_hold_s": self.scene_hold_s,
            "replay": self.replay,
            "replay_min_interval_s": self.replay_min_interval_s,
            "chapters": self.chapters,
        }


# ──────────────────────────────────────────────────────────────────────────────
# OBS client seam (real = obsws-python; tests inject a fake)
# ──────────────────────────────────────────────────────────────────────────────


class ObsRequestError(Exception):
    """OBS answered but refused the request (unknown request, not recording…).

    Non-fatal: the connection is still good.
    """


class ObsClient(Protocol):
    def save_replay_buffer(self) -> None: ...
    def current_scene(self) -> str: ...
    def set_scene(self, name: str) -> None: ...
    def set_text(self, source: str, text: str) -> None: ...
    def create_chapter(self, name: str) -> None: ...
    def close(self) -> None: ...


class _ObsWsClient:
    """Thin adapter over ``obsws_python.ReqClient`` (lazy import)."""

    def __init__(self, cfg: ObsBridgeConfig) -> None:
        # obsws-python logs "password='…'" at INFO on connect and puts it in
        # ReqClient.__repr__. Silence its logger; never repr the client.
        logging.getLogger("obsws_python").setLevel(logging.CRITICAL + 1)
        import obsws_python as obs  # optional extra: pip install -e ".[obs]"

        self._err = obs.error.OBSSDKRequestError
        self._c = obs.ReqClient(
            host=cfg.host,
            port=int(cfg.port),
            password=cfg.password,
            timeout=cfg.connect_timeout_s,
        )

    def _call(self, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except self._err as e:
            raise ObsRequestError(f"code={getattr(e, 'code', '?')}") from None

    def save_replay_buffer(self) -> None:
        self._call(self._c.save_replay_buffer)

    def current_scene(self) -> str:
        r = self._call(self._c.get_current_program_scene)
        return str(
            getattr(r, "current_program_scene_name", None) or getattr(r, "scene_name", "") or ""
        )

    def set_scene(self, name: str) -> None:
        self._call(lambda: self._c.set_current_program_scene(name))

    def set_text(self, source: str, text: str) -> None:
        self._call(lambda: self._c.set_input_settings(source, {"text": text}, True))

    def create_chapter(self, name: str) -> None:
        # OBS 30.2+, only while recording Hybrid MP4; otherwise OBS refuses.
        self._call(lambda: self._c.send("CreateRecordChapter", {"chapterName": name}))

    def close(self) -> None:
        try:
            self._c.disconnect()
        except Exception:
            pass


# ──────────────────────────────────────────────────────────────────────────────
# Observation parsing
# ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ScoreObservation:
    locked: bool
    home: int | None = None
    away: int | None = None
    text: str = ""

    @property
    def pair(self) -> tuple[int, int] | None:
        if self.locked and self.home is not None and self.away is not None:
            return (self.home, self.away)
        return None


def _int_or_none(v: Any) -> int | None:
    try:
        if v is None or isinstance(v, bool):
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def format_score_text(fb: dict[str, Any], home: int, away: int) -> str:
    """``"KC 21 - 14 BUF"`` in on-screen order when known, else home first."""
    ht = str(fb.get("home_team") or fb.get("home_team_raw") or "").strip()
    at = str(fb.get("away_team") or fb.get("away_team_raw") or "").strip()
    if fb.get("home_left") is False:
        left, ls, rs, right = at, away, home, ht
    else:
        left, ls, rs, right = ht, home, away, at
    return f"{left} {ls} - {rs} {right}".strip()


def observation_from_payload(payload: dict[str, Any] | None) -> ScoreObservation:
    """Fail-closed parse of a ``visual_context`` payload."""
    p = payload if isinstance(payload, dict) else {}
    if not bool(p.get("score_vlm_locked")):
        return ScoreObservation(locked=False)
    fb = p.get("football")
    if not isinstance(fb, dict):
        return ScoreObservation(locked=False)
    home = _int_or_none(fb.get("home_score"))
    away = _int_or_none(fb.get("away_score"))
    if home is None or away is None or not (0 <= home <= 199 and 0 <= away <= 199):
        return ScoreObservation(locked=False)
    return ScoreObservation(
        locked=True, home=home, away=away, text=format_score_text(fb, home, away)
    )


def _default_frame_stamp() -> dict[str, Any]:
    from qoresence.monitor.frame_hub import get_latest_stamp

    return get_latest_stamp()


# ──────────────────────────────────────────────────────────────────────────────
# Bridge
# ──────────────────────────────────────────────────────────────────────────────


class ObsBridge:
    def __init__(
        self,
        config: ObsBridgeConfig,
        *,
        client_factory: Callable[[ObsBridgeConfig], ObsClient] | None = None,
        frame_stamp: Callable[[], dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._factory = client_factory or _ObsWsClient
        self._frame_stamp = frame_stamp or _default_frame_stamp
        self._clock = clock

        # Mailbox (subscriber thread → worker). Tiny private lock; never held
        # across I/O, never held while anything is emitted.
        self._mail_lock = threading.Lock()
        self._mail: ScoreObservation | None = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._unsubscribe: Callable[[], None] | None = None

        # Worker-owned state
        self._client: ObsClient | None = None
        self._next_connect_at = 0.0
        self._backoff_s = _BACKOFF_START_S
        self._warned = False
        self._latest = ScoreObservation(locked=False)
        self._last_locked: tuple[int, int] | None = None
        self._shown_text: str | None = None  # last text pushed to OBS (None=unknown)
        self._last_replay_at: float | None = None
        self._scene_restore_to: str | None = None
        self._scene_restore_at = 0.0

        # Stats (read by /health; simple attribute reads are fine)
        self.connected = False
        self.actions = 0
        self.actions_by_kind: dict[str, int] = {}
        self.last_action = ""
        self._last_action_at: float | None = None
        self.last_error = ""
        self.events_seen = 0

    # ── bus side (enqueue only) ───────────────────────────────────────────────

    def on_event(self, event: Any) -> None:
        """Bus subscriber. Copies fields into the mailbox; never blocks on I/O."""
        try:
            et = getattr(event, "type", None)
            if getattr(et, "value", et) != "visual_context":
                return
            obs = observation_from_payload(getattr(event, "payload", None))
        except Exception:
            return
        with self._mail_lock:
            self._mail = obs
            self.events_seen += 1
        self._wake.set()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, bus: Any = None) -> None:
        if bus is not None and self._unsubscribe is None:
            self._unsubscribe = bus.subscribe(self.on_event)
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="obs-bridge", daemon=True)
            self._thread.start()
        log.info(
            "OBS bridge enabled → %s:%s text=%r scene=%r",
            self.config.host,
            self.config.port,
            self.config.text_source,
            self.config.scene or None,
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
        self._disconnect()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=0.5)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.step()
            except Exception as e:  # never kill the worker
                self._note_error(f"step: {type(e).__name__}")

    # ── core logic (synchronous; tests drive this directly) ──────────────────

    def step(self) -> None:
        """Drain the mailbox, keep OBS in sync, run timers."""
        with self._mail_lock:
            obs, self._mail = self._mail, None
        now = self._clock()
        if obs is not None:
            self._latest = obs
        self._ensure_connected(now)

        live = self._capture_live()
        pair = self._latest.pair if live else None
        desired = self._latest.text if pair is not None else ""

        if pair is not None and pair != self._last_locked:
            prev = self._last_locked
            self._last_locked = pair
            if prev is not None and sum(pair) > sum(prev):
                self._on_score_increase(prev, pair, desired, now)
            elif prev is not None:
                log.info("OBS bridge: locked score moved %s → %s (no replay)", prev, pair)

        self._sync_text(desired)
        self._maybe_restore_scene(now)

    def _capture_live(self) -> bool:
        try:
            st = self._frame_stamp() or {}
        except Exception:
            return False
        if not st.get("has_frame"):
            return False
        age = st.get("age_s")
        try:
            return age is not None and float(age) <= float(self.config.stale_capture_s)
        except (TypeError, ValueError):
            return False

    def _on_score_increase(
        self, prev: tuple[int, int], pair: tuple[int, int], text: str, now: float
    ) -> None:
        label = f"Score {prev[0]}-{prev[1]} -> {pair[0]}-{pair[1]}"
        log.info("OBS bridge: locked score change %s", label)
        if self.config.replay:
            if (
                self._last_replay_at is None
                or now - self._last_replay_at >= self.config.replay_min_interval_s
            ):
                if self._do("replay", lambda c: c.save_replay_buffer()):
                    self._last_replay_at = now
            else:
                log.debug("OBS bridge: replay save rate-limited")
        if self.config.scene:
            self._flash_scene(now)
        if self.config.chapters:
            self._do("chapter", lambda c: c.create_chapter(label), fatal=False)

    def _flash_scene(self, now: float) -> None:
        target = self.config.scene
        if self._scene_restore_to is not None:
            # Already flashing — just extend the hold.
            self._scene_restore_at = now + self.config.scene_hold_s
            return
        c = self._client
        if c is None:
            return
        try:
            cur = c.current_scene()
        except ObsRequestError:
            cur = ""
        except Exception as e:
            self._lost(e)
            return
        if cur == target:
            return
        if self._do("scene", lambda c: c.set_scene(target)):
            self._scene_restore_to = cur or None
            self._scene_restore_at = now + self.config.scene_hold_s

    def _maybe_restore_scene(self, now: float) -> None:
        back = self._scene_restore_to
        if back is None or now < self._scene_restore_at:
            return
        c = self._client
        if c is None:
            return
        try:
            cur = c.current_scene()
        except ObsRequestError:
            cur = self.config.scene
        except Exception as e:
            self._lost(e)
            return
        self._scene_restore_to = None
        # Respect a manual switch made during the hold.
        if cur == self.config.scene:
            self._do("scene_restore", lambda c: c.set_scene(back))

    def _sync_text(self, desired: str) -> None:
        if self._client is None or not self.config.text_source:
            return
        if desired == self._shown_text:
            return
        src = self.config.text_source
        if self._do("text" if desired else "text_blank", lambda c: c.set_text(src, desired)):
            self._shown_text = desired

    # ── connection ────────────────────────────────────────────────────────────

    def _ensure_connected(self, now: float) -> None:
        if self._client is not None or now < self._next_connect_at:
            return
        try:
            self._client = self._factory(self.config)
        except Exception as e:
            self._client = None
            self.connected = False
            self._next_connect_at = now + self._backoff_s
            self._backoff_s = min(self._backoff_s * 2.0, _BACKOFF_MAX_S)
            self._note_error(f"connect: {type(e).__name__}")
            if not self._warned:
                self._warned = True
                log.warning(
                    "OBS bridge: cannot reach OBS at %s:%s (%s). Qoresence keeps "
                    "running; retrying in the background.",
                    self.config.host,
                    self.config.port,
                    type(e).__name__,
                )
            return
        self.connected = True
        self._backoff_s = _BACKOFF_START_S
        self._shown_text = None  # unknown after (re)connect → resync
        self._warned = False
        log.info("OBS bridge: connected to %s:%s", self.config.host, self.config.port)

    def _lost(self, e: BaseException) -> None:
        self._note_error(f"connection: {type(e).__name__}")
        if not self._warned:
            self._warned = True
            log.warning("OBS bridge: lost OBS connection (%s); retrying", type(e).__name__)
        self._disconnect()
        self._next_connect_at = self._clock() + self._backoff_s

    def _disconnect(self) -> None:
        c, self._client = self._client, None
        self.connected = False
        self._shown_text = None
        if c is not None:
            try:
                c.close()
            except Exception:
                pass

    def _do(self, kind: str, fn: Callable[[ObsClient], Any], *, fatal: bool = True) -> bool:
        c = self._client
        if c is None:
            return False
        try:
            fn(c)
        except ObsRequestError as e:
            self._note_error(f"{kind}: refused {e}")
            log.debug("OBS bridge: %s refused by OBS (%s)", kind, e)
            return False
        except Exception as e:
            if fatal:
                self._lost(e)
            else:
                self._note_error(f"{kind}: {type(e).__name__}")
            return False
        self.actions += 1
        self.actions_by_kind[kind] = self.actions_by_kind.get(kind, 0) + 1
        self.last_action = kind
        self._last_action_at = self._clock()
        return True

    def _note_error(self, msg: str) -> None:
        pw = self.config.password
        if pw:
            msg = msg.replace(pw, "***")
        self.last_error = msg[:200]

    # ── health ────────────────────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        age = None
        if self._last_action_at is not None:
            age = round(self._clock() - self._last_action_at, 3)
        return {
            "enabled": True,
            "connected": bool(self.connected),
            "last_action": self.last_action,
            "last_action_age_s": age,
            "actions": int(self.actions),
            "actions_by_kind": dict(self.actions_by_kind),
            "last_error": self.last_error,
            "events_seen": int(self.events_seen),
            "showing_score": bool(self._shown_text),
            "config": self.config.public_dict(),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Process-wide handle (for /health)
# ──────────────────────────────────────────────────────────────────────────────

_BRIDGE: ObsBridge | None = None


def get_obs_bridge() -> ObsBridge | None:
    return _BRIDGE


def attach_health(body: dict[str, Any]) -> None:
    """Add ``obs_bridge`` to a /health body — only when the bridge is enabled."""
    b = _BRIDGE
    if b is not None:
        body["obs_bridge"] = b.stats()


def make_obs_bridge_from_config(
    config: ObsBridgeConfig | None, *, bus: Any = None
) -> ObsBridge | None:
    """Start the bridge when enabled; ``None`` (and no import of obsws) otherwise."""
    global _BRIDGE
    if config is None or not config.enabled:
        return None
    if _BRIDGE is not None:
        _BRIDGE.stop()
    bridge = ObsBridge(config)
    bridge.start(bus)
    _BRIDGE = bridge
    return bridge


def stop_obs_bridge() -> None:
    global _BRIDGE
    b, _BRIDGE = _BRIDGE, None
    if b is not None:
        b.stop()
