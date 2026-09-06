"""
Session memory for ClutchBot.

Writes a chronological log of agent actions, clutch moments, and the current
situation to a JSONL file. This becomes the source for post-stream digests,
highlight reels, and cross-session milestone tracking.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .moment_scorer import ScoredMoment
from .situation_model import SituationModel

log = logging.getLogger(__name__)


class SessionMemory:
    """Append-only memory of ClutchBot actions and game state snapshots."""

    def __init__(self, output_path: Path | None = None):
        self.output_path = output_path
        self._last_frame_seq: int | None = None
        self._last_entry: dict[str, Any] | None = None

    def last(self) -> dict[str, Any] | None:
        return self._last_entry

    def record(
        self,
        moment: ScoredMoment | None,
        situation: SituationModel,
        results: list[dict[str, Any]],
        *,
        stamp: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a clutch moment. Unstamped entries are refused (fail closed)."""
        from qoresence.sync.seqgate import accept_memory_write

        sit = situation.to_dict() if hasattr(situation, "to_dict") else dict(situation or {})
        candidate = dict(sit)
        if isinstance(stamp, dict):
            candidate.update(stamp)
        checked = accept_memory_write(candidate)
        if not checked["accepted"]:
            log.debug("SessionMemory refuse %s", checked.get("refuse"))
            return checked

        seq = int((checked["stamp"] or {}).get("frame_seq"))
        if self._last_frame_seq is not None and seq == self._last_frame_seq:
            return {
                "accepted": False,
                "refuse": "same_seq_noop",
                "stamp": checked["stamp"],
                "entry": None,
            }

        entry: dict[str, Any] = {
            "ts": time.time(),
            "ts_ns": time.time_ns(),
            "situation": sit,
            "results": results,
        }
        entry.update(checked["stamp"] or {})

        if moment:
            entry["moment"] = {
                "triggered": moment.triggered,
                "weight": moment.weight,
                "action": moment.action,
                "message": moment.message,
                "reason": moment.reason,
                "cooldown_key": moment.cooldown_key,
            }

        if self.output_path is None:
            self._last_frame_seq = seq
            self._last_entry = entry
            return {**checked, "entry": entry, "persisted": False}

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError as e:
            log.warning(f"SessionMemory write failed: {e}")
            return {**checked, "accepted": False, "refuse": "write_failed", "entry": entry}

        self._last_frame_seq = seq
        self._last_entry = entry
        return {**checked, "entry": entry, "persisted": True}

    def record_action(
        self,
        action: str,
        payload: dict[str, Any],
        situation: SituationModel,
        *,
        stamp: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a generic action."""
        return self.record(
            moment=None,
            situation=situation,
            results=[{"action": action, "payload": payload}],
            stamp=stamp,
        )
