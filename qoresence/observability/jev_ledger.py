"""Unified Jev judgment ledger — one append-only sink for observation packs.

Schema ``qoresence.jev.ledger.v0`` on plane ``qoresence-observation``. OCCF
land-order #1 (``docs/OCCF.md`` "Judgment ledger row"): every Jev judgment pack
keeps its private JSONL *and* dual-writes here so later slices (connector binds,
``jev_tail``) can query one file instead of a dozen.

Hard law:

- ``licenses_digits`` is False on every row, forever. The ledger never mints
  scores; a payload that tries is scrubbed to False.
- Default OFF. ``--jev-ledger`` / ``QORESENCE_JEV_LEDGER=1``, or under the Jev
  umbrella ``--jev`` / ``QORESENCE_JEV=1``. ``--play`` does not enable it.
- Append is best-effort and never raises into a pack hot path. The module takes
  only its own lock around the file append — no lobe locks, no bus emits.
- Unknown ``pack`` fails closed: rejected, nothing written.

``pack="connector"`` is written by the OCCF connector-bind engine
(``qoresence.observability.connector_bind``, ``--jev-connector``) — binds
exist only as ledger rows; there is no ``connector.jsonl``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "qoresence.jev.ledger.v0"
PLANE = "qoresence-observation"
DEFAULT_PATH = Path("logs/jev_ledger.jsonl")

# Known judgment packs. ``conductor`` aliases ``jev_conductor``; ``connector``
# is the OCCF connector-bind pack (qoresence.observability.connector_bind).
PACKS = frozenset(
    {
        "ticket_stale",
        "noul",
        "jev_conductor",
        "conductor",
        "press_labeler",
        "recap_hygiene",
        "sync_coroner",
        "score_plausibility",
        "ticket_glass",
        "sync_glass",
        "mint_verifier",
        "join_picker",
        "connector",
    }
)


def _env_enabled() -> bool:
    on = {"1", "true", "on", "yes"}
    return (
        os.environ.get("QORESENCE_JEV_LEDGER", "").strip().lower() in on
        or os.environ.get("QORESENCE_JEV", "").strip().lower() in on
    )


def _scrub_payload(payload: Any) -> Any:
    """Copy the payload; licenses_digits is scrubbed to False inside it too."""
    if isinstance(payload, dict):
        out = dict(payload)
        out["licenses_digits"] = False
        return out
    return {"value": payload}


class JevLedger:
    """Append-only JSONL sink for one file. A constructed ledger is opt-in."""

    def __init__(self, path: Any = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self._handle: Any = None
        self._lock = threading.Lock()
        self._written = 0
        self._rejected = 0

    def append(
        self,
        pack: str,
        verdict: Any = None,
        *,
        clock_ns: Any = None,
        frame_seq: Any = None,
    ) -> bool:
        """Append one ledger row. Returns False on unknown pack or IO error."""
        try:
            if pack not in PACKS:
                with self._lock:
                    self._rejected += 1
                return False
            if isinstance(verdict, dict):
                if clock_ns is None:
                    clock_ns = verdict.get("clock_ns")
                if frame_seq is None:
                    frame_seq = verdict.get("frame_seq")
            row = {
                "schema": SCHEMA,
                "plane": PLANE,
                "pack": pack,
                "clock_ns": clock_ns,
                "frame_seq": frame_seq,
                "licenses_digits": False,
                "verdict": _scrub_payload(verdict),
                "ts": time.time(),
            }
            line = json.dumps(row, separators=(",", ":"), default=str) + "\n"
            with self._lock:
                if self._handle is None:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self._handle = self.path.open("a", encoding="utf-8")
                self._handle.write(line)
                self._handle.flush()
                self._written += 1
            return True
        except Exception as e:
            log.debug("jev_ledger append skipped: %s", e)
            return False

    def read(self) -> Iterator[dict[str, Any]]:
        yield from read_judgments(self.path)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "path": str(self.path),
                "written": self._written,
                "rejected": self._rejected,
                "licenses_digits": False,
            }

    def close(self) -> None:
        with self._lock:
            if self._handle is not None:
                try:
                    self._handle.close()
                except Exception:
                    pass
                self._handle = None


def read_judgments(path: Any = DEFAULT_PATH) -> Iterator[dict[str, Any]]:
    """Iterate parsed ledger rows. Skips blank/corrupt lines; never raises."""
    try:
        p = Path(path)
        if not p.is_file():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if isinstance(row, dict):
                yield row
    except Exception:
        return


# ── module-level default sink (configured by CLI / env) ────────────────────

_enabled = False
_default: JevLedger | None = None
_default_lock = threading.Lock()


def ledger_enabled() -> bool:
    return _enabled or _env_enabled()


def configure_jev_ledger(
    *, enabled: bool | None = None, path: Any = None
) -> None:
    """Called once from CLI startup. ``enabled`` ORs with the env gates."""
    global _enabled, _default
    with _default_lock:
        if enabled is not None:
            _enabled = bool(enabled)
        if path is not None:
            if _default is not None:
                _default.close()
            _default = JevLedger(path)


def _default_ledger() -> JevLedger:
    global _default
    with _default_lock:
        if _default is None:
            _default = JevLedger(DEFAULT_PATH)
        return _default


def append_judgment(
    pack: str,
    verdict: Any = None,
    *,
    clock_ns: Any = None,
    frame_seq: Any = None,
) -> bool:
    """Dual-write hook packs call from their JSONL path. Never raises."""
    try:
        if not ledger_enabled():
            return False
        return _default_ledger().append(
            pack, verdict, clock_ns=clock_ns, frame_seq=frame_seq
        )
    except Exception:
        return False


def note_judgment(
    pack: str,
    verdict: Any = None,
    *,
    clock_ns: Any = None,
    frame_seq: Any = None,
) -> bool:
    """Alias of append_judgment — the name OCCF uses for ledger writes."""
    return append_judgment(
        pack, verdict, clock_ns=clock_ns, frame_seq=frame_seq
    )


def reset_jev_ledger() -> None:
    """Close the default sink and clear flags. Tests and shutdown only."""
    global _enabled, _default
    with _default_lock:
        if _default is not None:
            _default.close()
        _default = None
        _enabled = False
