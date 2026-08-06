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

    def record(
        self,
        moment: ScoredMoment | None,
        situation: SituationModel,
        results: list[dict[str, Any]],
    ) -> None:
        """Record a clutch moment and its execution results."""
        if self.output_path is None:
            return

        entry: dict[str, Any] = {
            "ts": time.time(),
            "ts_ns": time.time_ns(),
            "situation": situation.to_dict(),
            "results": results,
        }

        if moment:
            entry["moment"] = {
                "triggered": moment.triggered,
                "weight": moment.weight,
                "action": moment.action,
                "message": moment.message,
                "reason": moment.reason,
                "cooldown_key": moment.cooldown_key,
            }

        try:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            with self.output_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, separators=(",", ":")) + "\n")
        except OSError as e:
            log.warning(f"SessionMemory write failed: {e}")

    def record_action(
        self,
        action: str,
        payload: dict[str, Any],
        situation: SituationModel,
    ) -> None:
        """Record a generic action."""
        self.record(
            moment=None,
            situation=situation,
            results=[{"action": action, "payload": payload}],
        )
