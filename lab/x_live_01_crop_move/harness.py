#!/usr/bin/env python3
"""LAB / FIXTURE harness — X LIVE 0-1 crop_hash move silence.

NON-CLAIM. Python harness — CI Node 20 cannot import board.ts.
Does not start --play. Prints no secrets.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from overlay_gate import overlay_score_text
from pickboard_gate import pick_board, scorebug_pair, ticket_fresh
fixture = json.loads((HERE / "FIXTURE.json").read_text(encoding="utf-8"))
exit_code = 0


def fail(msg: str) -> None:
    global exit_code
    print(f"FAIL {msg}", file=sys.stderr)
    exit_code = 1


if fixture.get("label") != "FIXTURE" or fixture.get("kind") != "NON-CLAIM":
    fail("fixture must be labeled FIXTURE / NON-CLAIM")

receipt: dict = {
    "label": fixture.get("label"),
    "kind": fixture.get("kind"),
    "name": fixture.get("name"),
    "after": fixture.get("after"),
    "cases": [],
}

for c in fixture.get("cases") or []:
    snap = c["snapshot"]
    board = pick_board(snap, snap.get("situation") or {}, snap.get("confirm") or {}, snap.get("video") or {})
    pair = scorebug_pair(board["home"], board["away"])
    overlay = overlay_score_text(snap.get("situation") or {}, snap)
    row = {
        "id": c["id"],
        "pickBoard": {"home": board["home"], "away": board["away"], "locked": board["locked"]},
        "ingest": {
            "home": board["home"],
            "away": board["away"],
            "locked": board["locked"],
            "scorebug": pair,
        },
        "overlay_score": overlay,
    }
    receipt["cases"].append(row)
    exp = c["expect"]
    if board["home"] != exp["home"] or board["away"] != exp["away"] or board["locked"] != exp["locked"]:
        fail(f"{c['id']} pickBoard {row['pickBoard']} want {exp}")
    if pair != exp["scorebug"]:
        fail(f"{c['id']} scorebugPair {pair!r} want {exp['scorebug']!r}")
    if overlay != exp["overlay_score"]:
        fail(f"{c['id']} overlay {overlay!r} want {exp['overlay_score']!r}")

moved = next((c for c in fixture.get("cases") or [] if c["id"] == "stuck_01_crop_moved_silence"), None)
if moved:
    lc = moved["snapshot"]["confirm"]["last_confirm"]
    if lc["home_score"] != 0 or lc["away_score"] != 1:
        fail("silence case last_confirm must stay 0-1")
    if ticket_fresh(
        ticket_crop_hash=lc["crop_hash"],
        live_crop_hash=moved["snapshot"]["video"]["crop_hash"],
    ):
        fail("ticketFresh must be false after FrameHub crop_hash move")

print(json.dumps(receipt, indent=2))
if exit_code == 0:
    print("PASS x-live-01 crop_hash move silence", file=sys.stderr)
sys.exit(exit_code)
