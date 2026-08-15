#!/usr/bin/env python3
"""Download nflverse seasonal rosters into a local JSONL cache.

Public names only (CC-BY 4.0). Does not touch EA Madden files.
Usage:
    python scripts/sync_nfl_roster.py
    python scripts/sync_nfl_roster.py --season 2026 --out data/nfl/roster.jsonl
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# nflverse-data release assets (CSV). Tried in order.
_URLS = (
    "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.csv",
    "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster.csv",
)

_KEEP = (
    "full_name",
    "first_name",
    "last_name",
    "football_name",
    "jersey_number",
    "position",
    "team",
    "status",
    "gsis_id",
    "season",
)


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "qoresence-nfl-roster/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _rows_from_csv(blob: bytes, season: int) -> list[dict]:
    text = blob.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    out: list[dict] = []
    for raw in reader:
        row = {k: (raw.get(k) or "").strip() for k in _KEEP if k in (raw or {})}
        if "team" not in row and raw.get("team_abbr"):
            row["team"] = str(raw.get("team_abbr") or "").strip()
        if not row.get("full_name") and not row.get("last_name"):
            continue
        if season and str(raw.get("season") or "") not in {"", str(season)}:
            # yearly file may omit season or include only that year
            if raw.get("season") and str(raw.get("season")) != str(season):
                continue
        row["season"] = str(raw.get("season") or season)
        out.append(row)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Sync nflverse rosters for Madden 27 name matching")
    p.add_argument("--season", type=int, default=2026)
    p.add_argument("--out", default="data/nfl/roster.jsonl")
    args = p.parse_args()
    out_path = Path(args.out)
    last_err = None
    rows: list[dict] = []
    for tmpl in _URLS:
        url = tmpl.format(season=args.season)
        try:
            blob = _fetch(url)
            rows = _rows_from_csv(blob, args.season)
            if rows:
                print(f"fetched {len(rows)} players from {url}")
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            print(f"skip {url}: {e}")
    if not rows:
        print(f"sync failed: {last_err}", file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {out_path} ({len(rows)} rows)")
    print("Source: nflverse-data rosters · CC-BY 4.0 · not EA Madden")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
