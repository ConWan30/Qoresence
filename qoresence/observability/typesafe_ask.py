"""Shared TypeSafe ask helpers for observation-plane packs.

Mirrors TicketGlass / SyncGlass (#229) ask hygiene without forcing those packs
to import this module (do not regress glass):

- utf-8-sig key load from ``TYPESAFE_API_KEY`` or ``.secrets/typesafe.key``
- ``TypeSafeClient`` timeout (default 10s) + ``RetryPolicy(max_retries=0)``
- warn-once on failure (not silent forever, not spam)
- optional ask cadence + reuse of last good answers

Never logs the API key. Never licenses score digits.
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 10.0
DEFAULT_ASK_INTERVAL_S = 2.0
DEFAULT_REUSE_S = 15.0
KEY_PATH = Path(".secrets/typesafe.key")


def ensure_typesafe_key() -> bool:
    """Ensure ``TYPESAFE_API_KEY`` is set. Load from file with utf-8-sig if needed."""
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return True
    try:
        raw = KEY_PATH.read_text(encoding="utf-8-sig").strip()
        if not raw:
            return False
        os.environ["TYPESAFE_API_KEY"] = raw
        return True
    except Exception:
        return False


def key_present() -> bool:
    if os.environ.get("TYPESAFE_API_KEY", "").strip():
        return True
    try:
        return KEY_PATH.is_file() and bool(KEY_PATH.stat().st_size)
    except Exception:
        return False


def open_typesafe_client(
    *,
    model: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> Any | None:
    """Build a ``TypeSafeClient`` context manager with timeout + no retries.

    Returns None when the SDK is missing. Tolerates older SDK signatures.
    """
    try:
        from typesafe_sdk import TypeSafeClient
    except Exception:
        return None
    retry_kw: dict[str, Any] = {}
    try:
        from typesafe_sdk import RetryPolicy

        retry_kw["retry"] = RetryPolicy(max_retries=0)
    except Exception:
        pass
    try:
        if model:
            return TypeSafeClient(model=model, timeout=timeout_s, **retry_kw)
        return TypeSafeClient(timeout=timeout_s, **retry_kw)
    except TypeError:
        try:
            if model:
                return TypeSafeClient(model=model, timeout=timeout_s)
            return TypeSafeClient(timeout=timeout_s)
        except TypeError:
            try:
                return TypeSafeClient(model=model) if model else TypeSafeClient()
            except TypeError:
                return TypeSafeClient()


def system_one(
    *,
    state: dict[str, Any],
    questions: Any,
    model: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    warn_label: str = "typesafe",
    warned_flag: list[bool] | None = None,
    logger: logging.Logger | None = None,
) -> Any | None:
    """Call ``system_one`` once with timeout + warn-once. Returns response or None."""
    lg = logger or log
    if not ensure_typesafe_key():
        return None
    client_cm = open_typesafe_client(model=model, timeout_s=timeout_s)
    if client_cm is None:
        return None
    try:
        with client_cm as client:
            try:
                return client.system_one(
                    state=state, questions=questions, timeout=timeout_s
                )
            except TypeError:
                return client.system_one(state=state, questions=questions)
    except Exception as e:
        if warned_flag is None:
            lg.debug("%s system_one failed: %s", warn_label, e)
            return None
        if not warned_flag[0]:
            warned_flag[0] = True
            lg.warning(
                "%s system_one failed (%s): %s",
                warn_label,
                type(e).__name__,
                e,
            )
        else:
            lg.debug("%s system_one failed: %s", warn_label, e)
        return None


class AskCadence:
    """Glass-style ask interval + reuse last good vote between asks."""

    def __init__(
        self,
        *,
        ask_interval_s: float = DEFAULT_ASK_INTERVAL_S,
        reuse_s: float = DEFAULT_REUSE_S,
        warn_label: str = "typesafe",
    ) -> None:
        self.ask_interval_s = float(ask_interval_s)
        self.reuse_s = float(reuse_s)
        self.warn_label = warn_label
        self._last_ask_mono = 0.0
        self._last_ok_mono = 0.0
        self._last_answers: dict[str, Any] | None = None
        self.asks = 0
        self.fails = 0
        self.reuses = 0
        self._warned: list[bool] = [False]

    @property
    def warned(self) -> bool:
        return bool(self._warned[0])

    def ask_or_reuse(
        self,
        ask_fn: Callable[[], dict[str, Any] | None],
    ) -> dict[str, Any] | None:
        """Invoke ``ask_fn`` at most once per ask_interval; reuse last good."""
        now = time.monotonic()
        if (now - self._last_ask_mono) >= self.ask_interval_s:
            self._last_ask_mono = now
            self.asks += 1
            got = ask_fn()
            if got is not None:
                self._last_answers = dict(got)
                self._last_ok_mono = now
                return got
            self.fails += 1
        if (
            self._last_answers is not None
            and (now - self._last_ok_mono) < self.reuse_s
        ):
            self.reuses += 1
            return dict(self._last_answers)
        return None

    def mark_warned(self) -> list[bool]:
        """Mutable warn-once flag shared with ``system_one``."""
        return self._warned

    def stats(self) -> dict[str, Any]:
        return {
            "ask_interval_s": self.ask_interval_s,
            "reuse_s": self.reuse_s,
            "typesafe_asks": self.asks,
            "typesafe_fails": self.fails,
            "typesafe_reuses": self.reuses,
            "typesafe_warned": self.warned,
        }
