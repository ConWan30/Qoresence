"""Offline observation journal replay. No network, no VLM/Quicksilver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from qoresence.observation.lifecycle import (
    JOURNAL_SCHEMA,
    load_journal_lines,
    replay_journal,
)


def replay_file(path: Path, *, session_id: str | None = None) -> list[dict]:
    """Replay a durable journal and assert revision parity with recorded rows."""
    text = path.read_text(encoding="utf-8")
    rows = load_journal_lines(text)
    if not rows:
        return []
    if session_id is None:
        session_id = rows[0]["evidence"]["session_id"]
    return replay_journal(rows, session_id=session_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay an observation journal offline (no network)"
    )
    parser.add_argument("journal", type=Path, help="Path to observations.jsonl")
    parser.add_argument(
        "--session-id",
        default=None,
        help="Session id to verify (default: first journal row)",
    )
    args = parser.parse_args(argv)
    try:
        records = replay_file(args.journal, session_id=args.session_id)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"replay failed: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {len(records)} observation(s), schema={JOURNAL_SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
