"""Opt-in latency JSONL + in-memory summary.

Enable with ``QORESENCE_LATENCY_LOG=1``. Never raises into capture loops.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DEFAULT_DIR = Path("logs/latency")
_MAX_SAMPLES = 500


def _env_enabled() -> bool:
    return os.environ.get("QORESENCE_LATENCY_LOG", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


@dataclass
class LatencyStats:
    """Ring of per-name samples + optional JSONL."""

    enabled: bool = field(default_factory=_env_enabled)
    out_dir: Path = field(default_factory=lambda: DEFAULT_DIR)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _samples: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))
    )
    _counts: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _jsonl: Path | None = None

    def __post_init__(self) -> None:
        if self.enabled:
            try:
                self.out_dir.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d_%H%M%S")
                self._jsonl = self.out_dir / f"latency_{stamp}.jsonl"
            except Exception as e:
                log.debug("latency JSONL disabled: %s", e)
                self._jsonl = None

    def record(self, name: str, ms: float, **meta: Any) -> None:
        """Record one sample. Safe no-op when disabled; never raises."""
        try:
            if not self.enabled:
                return
            ms_f = float(ms)
            if ms_f < 0:
                ms_f = 0.0
            with self._lock:
                self._samples[name].append(ms_f)
                self._counts[name] += 1
                path = self._jsonl
            if path is not None:
                row = {
                    "ts": time.time(),
                    "name": name,
                    "ms": round(ms_f, 3),
                    **{k: v for k, v in meta.items() if v is not None},
                }
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, separators=(",", ":")) + "\n")
        except Exception:
            pass

    def summary(self) -> dict[str, Any]:
        """Return {name: {count, p50, p95, max_ms}} — works when disabled (empty)."""
        with self._lock:
            out: dict[str, Any] = {
                "enabled": self.enabled,
                "names": {},
            }
            for name, dq in self._samples.items():
                vals = sorted(dq)
                if not vals:
                    continue
                n = len(vals)

                def _pct(p: float) -> float:
                    if n == 1:
                        return vals[0]
                    idx = min(n - 1, max(0, int(round((p / 100.0) * (n - 1)))))
                    return vals[idx]

                out["names"][name] = {
                    "count": int(self._counts.get(name, n)),
                    "n_ring": n,
                    "p50_ms": round(_pct(50), 3),
                    "p95_ms": round(_pct(95), 3),
                    "max_ms": round(vals[-1], 3),
                }
            return out

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()
            self._counts.clear()


_stats: LatencyStats | None = None
_stats_lock = threading.Lock()


def get_latency_stats() -> LatencyStats:
    global _stats
    with _stats_lock:
        if _stats is None:
            _stats = LatencyStats()
        return _stats


def reset_latency_stats(*, enabled: bool | None = None) -> LatencyStats:
    global _stats
    with _stats_lock:
        en = _env_enabled() if enabled is None else bool(enabled)
        _stats = LatencyStats(enabled=en)
        return _stats


def record_latency(name: str, ms: float, **meta: Any) -> None:
    """Module helper — best-effort."""
    try:
        get_latency_stats().record(name, ms, **meta)
    except Exception:
        pass


@contextmanager
def latency_span(name: str, **meta: Any) -> Iterator[None]:
    """Context manager: record wall ms for a block."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000.0
        record_latency(name, ms, **meta)
