"""Stage-3 scoreboard replay eval: fixtures, runner, metrics, policies.

Everything here is offline: BoardObservation rows fold through the real
ScoreRecheck state machine. No VLM, TypeSafe, network, or capture hardware —
cached Jev verdicts ride the manifest rows and only feed injected suspicion.
"""

from __future__ import annotations

import json

import pytest

from qoresence.evals.scoreboard.manifest import (
    MANIFEST_SCHEMA,
    build_manifest_from_recording,
    discover_manifests,
    load_manifest,
    to_board,
    truth_pair_at,
)
from qoresence.evals.scoreboard.runner import run_fixture_dir, run_manifest


@pytest.fixture(scope="module")
def reports():
    return run_fixture_dir()


def _report(reports, name):
    for path, rep in reports.items():
        if path.endswith(name):
            return rep
    raise AssertionError(f"no report for {name}")


def _statuses(report, variant):
    return [e["status"] for e in report["variants"][variant]["events"]]


# ---------- manifest / fixture layer ----------

def test_fixtures_discover_and_load():
    paths = discover_manifests()
    names = {p.name for p in paths}
    assert {
        "clean_game.json",
        "ocr_echo.json",
        "evidence_failures.json",
        "bounded_recheck.json",
        "jev_policy.json",
    } <= names
    for p in paths:
        m = load_manifest(p)
        assert m["truth"] and m["observations"]
        assert m["end_ns"] > 0
        for row in m["observations"]:
            board = to_board(row)
            assert board.frame_seq > 0 and board.captured_ns > 0


def test_manifest_rejects_wrong_schema(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "other-0", "observations": []}))
    with pytest.raises(ValueError):
        load_manifest(bad)


def test_truth_pair_lookup():
    m = load_manifest(discover_manifests()[0])
    t = m["truth"]
    assert truth_pair_at(t, -1) is None
    first = t[0]
    assert truth_pair_at(t, int(first["start_ns"])) == (
        first["home_score"], first["away_score"],
    )


# ---------- determinism / parity ----------

def test_replay_is_deterministic(reports):
    assert reports
    for rep in reports.values():
        assert rep["deterministic_replay"] is True


# ---------- scenario coverage ----------

def test_clean_game_no_wrong_paints(reports):
    rep = _report(reports, "clean_game.json")
    for variant, res in rep["variants"].items():
        assert res["paints"]["wrong"] == 0, variant
        # Stale-window cost only: the last paint persists until the next
        # read lands after each truth boundary (0.7s + 1.2s + 1.2s).
        # Every variant pays the same honest cost on clean evidence.
        assert res["exposure_ns"]["wrong_ns"] == 3_100_000_000, variant
    det = rep["variants"]["deterministic"]
    assert all(s == "accepted" for s in _statuses(rep, "deterministic"))
    assert all(s["confirmed"] for s in det["segments"])


def test_ocr_echo_held_by_recheck_variants(reports):
    rep = _report(reports, "ocr_echo.json")
    # Legacy and the floor-only baseline both paint the 20-20 echo.
    assert rep["variants"]["legacy"]["paints"]["wrong"] == 1
    assert rep["variants"]["baseline"]["paints"]["wrong"] == 1
    # Suspicion layers hold it; a later same-frame 20-0 keeps truth painted.
    for v in ("deterministic", "typesafe", "combined"):
        res = rep["variants"][v]
        assert res["paints"]["wrong"] == 0, v
        assert res["exposure_ns"]["wrong_ns"] == 0, v
        assert "recheck" in res["status_counts"], v
    det = rep["variants"]["deterministic"]
    assert _statuses(rep, "deterministic") == [
        "accepted", "accepted", "recheck", "accepted", "accepted",
    ]
    assert det["final_exposed"] == [20, 0]


def test_evidence_floor_statuses(reports):
    rep = _report(reports, "evidence_failures.json")
    det = rep["variants"]["deterministic"]
    counts = det["status_counts"]
    assert counts["duplicate"] == 1
    assert counts["out_of_order"] == 1
    assert counts["stale"] == 1
    assert counts["missing_evidence"] == 1
    assert counts["scene_unknown"] == 1
    # Legacy paints every bad row: 5 wrong paints vs the floor's single
    # wrong paint (the team-swap rebaseline every policy shares).
    assert rep["variants"]["legacy"]["paints"]["wrong"] == 5
    assert det["paints"]["wrong"] == 1
    assert det["status_counts"]["accepted"] == 3


def test_bounded_recheck_exhaustion_and_recovery(reports):
    rep = _report(reports, "bounded_recheck.json")
    det = rep["variants"]["deterministic"]
    statuses = _statuses(rep, "deterministic")
    assert statuses[:5] == [
        "accepted", "recheck", "recheck", "exhausted", "accepted",
    ]
    # Exhaustion surfaces the last disagreeing candidate — bounded, not
    # hidden — so it shows up as exactly one wrong paint.
    assert det["paints"]["wrong"] == 1
    assert rep["variants"]["legacy"]["paints"]["wrong"] == 4
    # The both-sides-scored 20-13 needed a corroborating frame: the real
    # transition still lands, just ~2s late.
    seg = [s for s in det["segments"] if s["pair"] == [20, 13]][0]
    assert seg["confirmed"] is True
    assert seg["first_correct_latency_ns"] == 4_200_000_000


def test_jev_policy_contrast_and_recording(reports):
    rep = _report(reports, "jev_policy.json")
    ts = rep["variants"]["typesafe"]
    det = rep["variants"]["deterministic"]
    # Jev false-positive: flags the real 3-0 FG (noul .92), so typesafe holds
    # one cycle where deterministic accepts immediately.
    assert _statuses(rep, "typesafe")[1] == "recheck"
    assert _statuses(rep, "deterministic")[1] == "accepted"
    # Jev clears the real both-scored 10-14 (noul .12): typesafe paints at
    # once while delta-law rechecks and corroborates on the next frame.
    assert _statuses(rep, "typesafe")[4] == "accepted"
    assert _statuses(rep, "deterministic")[4] == "recheck"
    assert _statuses(rep, "deterministic")[5] == "accepted"
    # Row without a verdict falls back to the delta law (10-10 drop held).
    assert _statuses(rep, "typesafe")[6] == "recheck"
    # Every consult recorded with raw noul + composed decision.
    calls = ts["judgment_calls"]
    assert len(calls) == 7
    by_seq = {c["cand_seq"]: c for c in calls}
    assert by_seq[502]["noul"] == 0.92 and by_seq[502]["decided_suspicious"]
    assert by_seq[505]["noul"] == 0.12 and not by_seq[505]["decided_suspicious"]
    assert by_seq[507]["noul"] is None
    assert by_seq[507]["fallback"] == "delta_law"


def test_no_board_and_unparsed(tmp_path):
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_id": "s",
        "game_profile": "",
        "end_ns": 10_000_000_000,
        "truth": [
            {"start_ns": 0, "home_score": 7, "away_score": 0, "readable": True}
        ],
        "observations": [
            {"frame_seq": 1, "captured_ns": 1_000_000_000, "session_id": "s",
             "crop_hash": "c1", "home_team": "LOU", "away_team": "NCST",
             "home_score": None, "away_score": 0, "scene": "gameplay",
             "arrival_delay_ns": 0},
        ],
    }
    rep = run_manifest(manifest)
    assert rep["variants"]["deterministic"]["status_counts"]["no_board"] == 1
    assert rep["variants"]["legacy"]["status_counts"]["unparsed"] == 1


def test_unreadable_truth_segment_is_ambiguous(tmp_path):
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_id": "s",
        "game_profile": "",
        "end_ns": 10_000_000_000,
        "truth": [
            {"start_ns": 0, "home_score": 7, "away_score": 0, "readable": True},
            {"start_ns": 5_000_000_000, "home_score": 7, "away_score": 0,
             "readable": False},
        ],
        "observations": [],
    }
    rep = run_manifest(manifest)
    amb = rep["variants"]["deterministic"]["exposure_ns"]["ambiguous_ns"]
    assert amb == 5_000_000_000


# ---------- recording → manifest fold ----------

def test_build_manifest_from_recording(tmp_path):
    rec = tmp_path / "session.jsonl"
    rows = [
        {"home_score": 7, "away_score": 0, "left_team": "LOU",
         "right_team": "NCST", "quarter": 1, "clock": "12:00",
         "recorded_ns": 1_500_000_000, "recheck_status": "accepted",
         "_observation": {"session_id": "live-1", "seq": 11,
                          "clock_ns": 1_000_000_000, "crop_hash": "crop-11",
                          "game_state": "gameplay",
                          "analyzed_crop_hash": "sha-x"}},
        {"home_score": 7, "away_score": 0, "left_team": "LOU",
         "right_team": "NCST", "quarter": 1, "clock": "11:40",
         "recorded_ns": 3_400_000_000, "recheck_status": "accepted",
         "_observation": {"session_id": "live-1", "seq": 12,
                          "clock_ns": 3_000_000_000, "crop_hash": "crop-12",
                          "game_state": "gameplay",
                          "analyzed_crop_hash": "sha-y"}},
    ]
    rec.write_text("".join(json.dumps(r) + "\n" for r in rows))
    manifest = build_manifest_from_recording(
        rec,
        truth=[{"start_ns": 0, "home_score": 7, "away_score": 0,
                "readable": True}],
    )
    assert manifest["schema"] == MANIFEST_SCHEMA
    assert manifest["session_id"] == "live-1"
    obs = manifest["observations"]
    assert obs[0]["frame_seq"] == 11
    assert obs[0]["crop_hash"] == "crop-11"
    # analyzed blob hash stays diagnostic — never the source crop_hash.
    assert obs[0]["analyzed_crop_hash"] == "sha-x"
    assert obs[0]["arrival_delay_ns"] == 500_000_000
    rep = run_manifest(manifest)
    assert rep["deterministic_replay"] is True
    assert rep["variants"]["deterministic"]["paints"]["wrong"] == 0


def test_record_replay_row_env_gated(tmp_path, monkeypatch):
    from qoresence.vision.scoreboard_vlm import _record_replay_row

    log_path = tmp_path / "rows.jsonl"
    monkeypatch.delenv("QORESENCE_SCORE_REPLAY_LOG", raising=False)
    _record_replay_row({"home_score": 7}, "accepted")
    assert not log_path.exists()
    monkeypatch.setenv("QORESENCE_SCORE_REPLAY_LOG", str(log_path))
    _record_replay_row(
        {"home_score": 7, "_observation": {"seq": 3, "clock_ns": 5}},
        "recheck",
    )
    row = json.loads(log_path.read_text().strip())
    assert row["home_score"] == 7
    assert row["recheck_status"] == "recheck"
    assert row["recorded_ns"] > 0
    assert row["_observation"]["seq"] == 3


def test_fixture_dir_returns_all_reports(reports):
    assert len(reports) >= 5
    for rep in reports.values():
        assert rep["schema"] == "qoresence-score-replay-report-0"
        assert rep["comparison"]
