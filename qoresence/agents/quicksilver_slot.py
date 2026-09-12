"""One outbound call to api.quicksilverpro.io at a time.

ClutchFeed (muse-spark-1.3), MatchAgent, scoreboard VLM, and Visual VLM
share the same host+key. Parallel 6s/10s/30s POSTs all Read-timeout and
none of the mouths stay live.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_lock = threading.Lock()
_busy = threading.Event()


@contextmanager
def acquire_quicksilver(wait_s: float = 14.0) -> Iterator[bool]:
    """Yield True if this thread owns the slot. False = skip the POST."""
    got = _lock.acquire(timeout=max(0.05, float(wait_s)))
    if got:
        _busy.set()
    try:
        yield bool(got)
    finally:
        if got:
            _busy.clear()
            _lock.release()


def quicksilver_busy() -> bool:
    return _busy.is_set()
