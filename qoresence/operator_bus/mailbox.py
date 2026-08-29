"""Bounded JSONL mailbox. HTTP/file producers only enqueue. No bus fan-out."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections import deque
from pathlib import Path
from typing import Any

from qoresence.operator_bus.envelope import OperatorEnvelope, parse_envelope

log = logging.getLogger(__name__)

_CAPACITY = 200


def _default_root() -> Path:
    env = os.environ.get("QORESENCE_OPERATOR_BUS_DIR", "").strip()
    if env:
        return Path(env)
    return Path("logs") / "operator_bus"


class OperatorMailbox:
    """Drop-oldest inbox/outbox. Callers must not emit on RetinaEventBus from here."""

    def __init__(self, root: Path | None = None, capacity: int = _CAPACITY) -> None:
        self._lock = threading.Lock()
        self.root = Path(root) if root is not None else _default_root()
        self._inbox: deque[dict[str, Any]] = deque(maxlen=max(16, int(capacity)))
        self._outbox: deque[dict[str, Any]] = deque(maxlen=max(16, int(capacity)))
        self._inbox_path = self.root / "inbox.jsonl"
        self._outbox_path = self.root / "outbox.jsonl"
        self._load()

    def _load(self) -> None:
        for path, q in ((self._inbox_path, self._inbox), (self._outbox_path, self._outbox)):
            if not path.is_file():
                continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines()[-_CAPACITY:]:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        q.append(obj)
            except Exception as e:
                log.debug("operator bus load %s: %s", path, e)

    def _append(self, path: Path, row: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
        except Exception as e:
            log.debug("operator bus append %s: %s", path, e)

    def enqueue_inbox(self, raw: dict[str, Any]) -> OperatorEnvelope:
        env = parse_envelope(raw)
        row = env.to_dict()
        with self._lock:
            self._inbox.append(row)
        self._append(self._inbox_path, row)
        return env

    def enqueue_outbox(self, raw: dict[str, Any]) -> OperatorEnvelope:
        env = parse_envelope(raw)
        row = env.to_dict()
        with self._lock:
            self._outbox.append(row)
        self._append(self._outbox_path, row)
        return env

    def peek_inbox(self, n: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._inbox)
        return rows[-max(1, int(n)) :]

    def peek_outbox(self, n: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = list(self._outbox)
        return rows[-max(1, int(n)) :]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "inbox": len(self._inbox),
                "outbox": len(self._outbox),
                "dir": str(self.root),
                "last_inbox_id": self._inbox[-1]["id"] if self._inbox else None,
                "last_outbox_id": self._outbox[-1]["id"] if self._outbox else None,
            }


_box: OperatorMailbox | None = None
_box_lock = threading.Lock()


def get_operator_mailbox() -> OperatorMailbox:
    global _box
    with _box_lock:
        if _box is None:
            _box = OperatorMailbox()
        return _box


def reset_operator_mailbox() -> None:
    global _box
    with _box_lock:
        _box = None
