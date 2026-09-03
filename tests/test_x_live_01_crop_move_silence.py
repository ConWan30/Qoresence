"""LAB / FIXTURE — X LIVE 0-1 crop_hash move silence.

NON-CLAIM. After #152 (374e940) pickBoard gate and #153 (7a7393f) docs.
Does not start --play. Does not print secrets.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB = ROOT / "lab" / "x_live_01_crop_move"
FIXTURE_PATH = LAB / "FIXTURE.json"
HARNESS = LAB / "harness.py"
BOARD_TS = ROOT / "glass" / "src" / "lib" / "coupling" / "board.ts"
OVERLAY = ROOT / "qoresence" / "deck" / "overlay.html"
DOCS = ROOT / "docs" / "X_LIVE_STUDIO.md"

sys.path.insert(0, str(LAB))
from overlay_gate import overlay_score_text  # noqa: E402
from pickboard_gate import pick_board, scorebug_pair, ticket_fresh  # noqa: E402


def _fixture() -> dict:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert data["label"] == "FIXTURE"
    assert data["kind"] == "NON-CLAIM"
    assert data["after"]["pr_152_pickBoard"] == "374e940"
    assert data["after"]["pr_153_docs"] == "7a7393f"
    return data


def _case(fid: str) -> dict:
    for row in _fixture()["cases"]:
        if row["id"] == fid:
            return row
    raise AssertionError(f"missing fixture case {fid}")


def test_fixture_is_labeled_non_claim():
    fx = _fixture()
    assert "merge" in fx["out_of_scope"]
    assert "--play" in fx["out_of_scope"]
    assert "--x-glass" in fx["out_of_scope"]
    assert "glass/src/lib/coupling/board.ts" in fx["refs"]
    assert "docs/X_LIVE_STUDIO.md" in fx["refs"]


def test_docs_x_live_studio_still_blank_beats_hold():
    text = DOCS.read_text(encoding="utf-8")
    assert "blank beats hold" in text
    assert "crop_hash" in text
    assert "pickBoard" in text
    assert "score_vlm_locked" in text


def test_board_ts_still_has_ticket_fresh_crop_gate():
    """Python harness ports pickBoard; board.ts remains the shared glass gate."""
    src = BOARD_TS.read_text(encoding="utf-8")
    assert "export function ticketFresh(" in src
    assert "export function pickBoard(" in src
    assert "liveCrop && liveCrop !== ticketCrop" in src
    assert "Blank beats hold" in src


def test_pickboard_gate_stuck_01_crop_move_is_silent():
    snap = _case("stuck_01_crop_moved_silence")["snapshot"]
    lc = snap["confirm"]["last_confirm"]
    assert (lc["home_score"], lc["away_score"]) == (0, 1)
    assert ticket_fresh(ticket_crop_hash=lc["crop_hash"], live_crop_hash=snap["video"]["crop_hash"]) is False
    board = pick_board(snap, snap["situation"], snap["confirm"], snap["video"])
    assert board == {"home": None, "away": None, "locked": False}
    assert scorebug_pair(board["home"], board["away"]) == ""


def test_overlay_html_still_has_crop_mismatch_gate():
    html = OVERLAY.read_text(encoding="utf-8")
    assert "function digitsLicensed(" in html
    gate = html.split("function digitsLicensed")[1].split("function handle")[0]
    assert "crop_hash" in gate
    assert "ticketCrop!==liveCrop" in gate.replace(" ", "")
    assert "scoreboard_locked" not in gate


def test_overlay_gate_fresh_01_paints():
    snap = _case("control_fresh_01_paints")["snapshot"]
    assert overlay_score_text(snap["situation"], snap) == "0-1"


def test_overlay_gate_stuck_01_crop_move_is_silent():
    """Shared overlay digits EMPTY when confirm stays 0-1 and crop_hash moves."""
    snap = _case("stuck_01_crop_moved_silence")["snapshot"]
    lc = snap["confirm"]["last_confirm"]
    assert (lc["home_score"], lc["away_score"]) == (0, 1)
    assert lc["crop_hash"] == "crop-was"
    assert snap["situation"]["crop_hash"] == "crop-now"
    assert overlay_score_text(snap["situation"], snap) == ""


def test_overlay_observation_framehub_video_only_reads_situation_crop():
    """overlay.html liveCrop is situation.crop_hash — lab observation, not a claim."""
    row = _case("stuck_01_framehub_video_only_pickboard")
    assert row.get("observe_overlay_last_good") is True
    snap = row["snapshot"]
    assert snap["video"]["crop_hash"] == "crop-now"
    assert snap["situation"]["crop_hash"] == "crop-was"
    assert overlay_score_text(snap["situation"], snap) == "0-1"


def test_harness_does_not_import_board_ts():
    assert HARNESS.suffix == ".py"
    assert HARNESS.name == "harness.py"
    body = HARNESS.read_text(encoding="utf-8")
    assert "from pickboard_gate import" in body
    assert "from overlay_gate import" in body


def test_harness_exits_zero():
    """CI Node 20 cannot strip TypeScript — run the Python harness."""
    r = subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    receipt = json.loads(r.stdout)
    assert receipt["label"] == "FIXTURE"
    assert receipt["kind"] == "NON-CLAIM"
    by_id = {row["id"]: row for row in receipt["cases"]}
    silence = by_id["stuck_01_crop_moved_silence"]
    assert silence["pickBoard"] == {"home": None, "away": None, "locked": False}
    assert silence["ingest"]["scorebug"] == ""
    assert silence["overlay_score"] == ""
    framehub = by_id["stuck_01_framehub_video_only_pickboard"]
    assert framehub["pickBoard"]["locked"] is False
    assert framehub["pickBoard"]["home"] is None
    assert framehub["overlay_score"] == "0-1"
