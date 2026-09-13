"""Rebuild session-recap-1 from civif session.jsonl after Deck is down.

  python scripts/rebuild_recap_from_jsonl.py --session qoresence_3ea6449b913f
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qoresence.foundry.recap_store import rebuild_and_write  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Rebuild Recap from session.jsonl")
    p.add_argument("--session", required=True)
    p.add_argument("--jsonl", default=str(ROOT / "logs" / "civif" / "session.jsonl"))
    p.add_argument("--out", default="")
    args = p.parse_args()
    result = rebuild_and_write(
        session_id=args.session,
        jsonl_path=args.jsonl,
        dest=args.out or None,
        persist_enabled=True,
    )
    recap = result["recap"]
    print(json.dumps({  # noqa: T201
        "path": result["path"],
        "schema": recap.get("schema"),
        "session": recap.get("session"),
        "status": recap.get("status"),
        "event_count": recap.get("event_count"),
        "confirmed_event_count": recap.get("confirmed_event_count"),
        "linked_clip_count": recap.get("linked_clip_count"),
        "duration_ms": recap.get("duration_ms"),
    }, indent=2))
    return 0 if result["path"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
