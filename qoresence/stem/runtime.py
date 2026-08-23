"""Process-wide Retina Stem runtime (conductor + optional audio / record)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from qoresence.core.unified_config import StemConfig
from qoresence.stem.audio import StemAudio
from qoresence.stem.conductor import StemConductor
from qoresence.stem.record import StemRecord

log = logging.getLogger(__name__)

_lock = threading.Lock()
_runtime: StemRuntime | None = None


class StemRuntime:
    def __init__(
        self,
        config: StemConfig,
        bus: Any | None = None,
        *,
        situation_provider: Callable[[], dict[str, Any]] | None = None,
        session_head_ns: int | None = None,
    ) -> None:
        self.config = config
        self.bus = bus
        self.conductor = StemConductor(
            bus,
            situation_provider=situation_provider,
            session_head_ns=session_head_ns,
        )
        self.audio = StemAudio(bus, session_head_ns=session_head_ns) if config.audio else None
        self.record = (
            StemRecord(bus, out_dir=config.record_dir, session_head_ns=session_head_ns)
            if config.record
            else None
        )

    def start(self) -> None:
        if self.config.conductor:
            self.conductor.start()
        if self.audio is not None:
            self.audio.start()
        if self.record is not None:
            self.record.start()

    def stop(self) -> None:
        self.conductor.stop()
        if self.audio is not None:
            self.audio.stop()
        if self.record is not None:
            self.record.stop()

    def health(self) -> dict[str, Any]:
        audio = self.audio.snapshot() if self.audio is not None else {"enabled": False}
        record = self.record.snapshot() if self.record is not None else {"active": False}
        snap = self.conductor.snapshot()
        return {
            "conductor": bool(self.config.conductor),
            "mode": snap.get("mode"),
            "why": snap.get("why"),
            "program": bool(self.config.program),
            "audio": audio,
            "record": record,
        }


def start_stem(
    config: StemConfig,
    bus: Any | None = None,
    *,
    situation_provider: Callable[[], dict[str, Any]] | None = None,
    session_head_ns: int | None = None,
) -> StemRuntime:
    global _runtime
    rt = StemRuntime(
        config,
        bus,
        situation_provider=situation_provider,
        session_head_ns=session_head_ns,
    )
    with _lock:
        _runtime = rt
    rt.start()
    return rt


def get_stem_runtime() -> StemRuntime | None:
    return _runtime


def stop_stem() -> None:
    global _runtime
    with _lock:
        rt = _runtime
        _runtime = None
    if rt is not None:
        rt.stop()
