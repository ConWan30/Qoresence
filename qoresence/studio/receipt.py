"""ReelReceipt sidecar — local proof that a render came from Qoresence data."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ReelReceipt:
    """Immutable(ish) record linking an LTX output to a Qoresence chapter."""

    session_id: str = ""
    clock_ns: int = 0
    source_clip: str = ""
    source_t_s: float = 0.0
    ltx_job_id: str = ""
    ltx_prompt: str = ""
    ltx_payload_hash: str = ""
    output_path: str = ""
    output_url: str = ""
    created_ns: int = 0
    completed_ns: int = 0
    status: str = "pending"
    error: str = ""
    game_profile: str = ""
    chapter_kind: str = ""
    chapter_label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "clock_ns": self.clock_ns,
            "source_clip": self.source_clip,
            "source_t_s": self.source_t_s,
            "ltx_job_id": self.ltx_job_id,
            "ltx_prompt": self.ltx_prompt,
            "ltx_payload_hash": self.ltx_payload_hash,
            "output_path": self.output_path,
            "output_url": self.output_url,
            "created_ns": self.created_ns,
            "completed_ns": self.completed_ns,
            "status": self.status,
            "error": self.error,
            "game_profile": self.game_profile,
            "chapter_kind": self.chapter_kind,
            "chapter_label": self.chapter_label,
            "metadata": self.metadata,
        }


def write_receipt(output_path: str | Path, receipt: ReelReceipt) -> Path:
    """Write `<output>.receipt.json` next to the rendered video."""
    output_path = Path(output_path)
    receipt_path = output_path.with_name(output_path.stem + ".receipt.json")
    receipt_path.write_text(json.dumps(receipt.to_dict(), indent=2), encoding="utf-8")
    return receipt_path


def now_ns() -> int:
    return time.time_ns()
