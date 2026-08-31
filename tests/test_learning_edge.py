"""Learning-edge: constraint schema, unit gate, correction, splitter, closed lanes."""

from __future__ import annotations

import pytest

from qoresence.agents.blast_radius import closed_lane_snapshot, lane_allows
from qoresence.agents.drive_graph import DriveGraph
from qoresence.agents.learning_constraint import (
    CONSTRAINT_KINDS,
    DEFAULT_CONSTRAINT_LOG,
    LearningConstraint,
    append_constraint,
    from_accepted_confirm,
    load_constraints,
    parse_constraint_record,
)
from qoresence.agents.learning_edge import (
    ENV_NAME,
    SplitterInputs,
    apply_constraints,
    closeout_applied,
    enabled,
    load_applicable,
    maybe_record_on_resolve,
    overlay_crops,
    reset_applied,
    split_chapter_units,
)
from qoresence.agents.unit_graph import (
    RETRY_CAP,
    CheckResult as GateResult,
    Unit,
    correct_units,
    evaluate_unit,
)
from qoresence.core.unified_config import RetinaUnifiedConfig
from qoresence.vision.confirm_ticket import mint_confirm_ticket
from qoresence.vision.scorebug_crops import (
    CFB_PRIMARY_SCOREBUG,
    CFB_SCOREBUG_CROPS,
    MADDEN_PRIMARY_SCOREBUG,
    scorebug_crops_for_profile,
)


def _ticket(**kw):
    return mint_confirm_ticket(
        session_id=kw.get("session_id", "sess_p1"),
        clock_ns=kw.get("clock_ns", 1_000),
        home_score=kw.get("home_score", 21),
        away_score=kw.get("away_score", 14),
        source=kw.get("source", "deepseek"),
        frame_seq=kw.get("frame_seq", 12),
    )


@pytest.fixture(autouse=True)
def _flag_off(monkeypatch):
    monkeypatch.delenv(ENV_NAME, raising=False)
    monkeypatch.delenv("QORESENCE_LEARNING_CONSTRAINTS_PATH", raising=False)
    reset_applied()
    yield
    reset_applied()


def _td_events():
    t0 = 0
    return [
        {
            "clock_ns": t0,
            "kind": "fast_chat",
            "path": "fast",
            "message": "Live-board 0-0",
            "coupling": 0.9,
            "factual": False,
        },
        {
            "clock_ns": t0 + 10_000,
            "kind": "fast_chat",
            "path": "fast",
            "message": "board dump",
            "coupling": 0.8,
            "factual": False,
        },
        {
            "clock_ns": t0 + int(20e9),
            "kind": "confirm_score",
            "path": "confirm",
            "message": "touchdown 7-0",
            "factual": True,
        },
        {
            "clock_ns": t0 + int(21e9),
            "kind": "prediction_resolve",
            "path": "confirm",
            "message": "TD resolved",
            "factual": True,
        },
    ]


# ── P1 schema ──────────────────────────────────────────────────────────────


def test_missing_mint_returns_none():
    crop = list(CFB_PRIMARY_SCOREBUG)
    assert from_accepted_confirm(None, evidence={"crop": crop}) is None
    assert from_accepted_confirm(None, source_ticket_id="", payload={"crop": crop}) is None
    assert (
        from_accepted_confirm(
            None,
            source_ticket_id="   ",
            kind="crop_band",
            payload={"crop": crop},
        )
        is None
    )


def test_good_confirm_plus_crop_evidence_is_crop_band():
    ticket = _ticket()
    c = from_accepted_confirm(
        ticket,
        evidence={
            "crop": list(CFB_PRIMARY_SCOREBUG),
            "frame_seq": 12,
            "lock": True,
            "climax": 0.4,
            "profile": "ncaa_football_27",
        },
        drive_id="drive_1",
    )
    assert c is not None
    assert isinstance(c, LearningConstraint)
    assert c.kind == "crop_band"
    assert c.source_ticket_id == ticket.ticket_id
    assert c.frozen is False
    assert c.plane == "qoresence-observation"
    assert c.target == "scorebug_crops"
    assert c.payload["crop"] == [0.12, 0.88, 0.78, 0.93]
    assert "home_score" not in c.payload


def test_score_pair_in_payload_rejected():
    ticket = _ticket()
    crop = list(CFB_PRIMARY_SCOREBUG)
    assert (
        from_accepted_confirm(
            ticket,
            kind="crop_band",
            payload={"crop": crop, "note": "locked 21-14"},
        )
        is None
    )
    assert (
        from_accepted_confirm(
            ticket,
            kind="crop_band",
            payload={"crop": crop, "home_score": 21, "away_score": 14},
        )
        is None
    )


def test_jsonl_round_trip(tmp_path):
    ticket = _ticket()
    c = from_accepted_confirm(
        ticket,
        kind="crop_band",
        payload={"crop": list(CFB_PRIMARY_SCOREBUG), "profile": "ncaa_football_27"},
        evidence={"frame_seq": 9, "lock": True},
        drive_id="drive_rt",
    )
    assert c is not None
    path = tmp_path / "learning_constraints.jsonl"
    written = append_constraint(c, path=path)
    assert written == path
    loaded = load_constraints(path)
    assert len(loaded) == 1
    assert loaded[0].id == c.id
    assert parse_constraint_record(loaded[0].to_dict()).id == c.id


def test_unknown_kind_rejected():
    ticket = _ticket()
    assert (
        from_accepted_confirm(
            ticket, kind="narrator", payload={"crop": list(CFB_PRIMARY_SCOREBUG)}
        )
        is None
    )


def test_frozen_field_write_rejected():
    ticket = _ticket()
    crop = list(CFB_PRIMARY_SCOREBUG)
    assert (
        from_accepted_confirm(
            ticket, kind="crop_band", target="qortroller-truth", payload={"crop": crop}
        )
        is None
    )


def test_kinds_are_the_six_writable_and_default_log_is_pilot():
    assert CONSTRAINT_KINDS == {
        "crop_band",
        "hysteresis",
        "rank_weight",
        "try_open",
        "schedule_skip",
        "freeze_weight",
    }
    assert DEFAULT_CONSTRAINT_LOG.as_posix() == "logs/pilot/learning_constraints.jsonl"


def test_ticketless_jsonl_line_dropped(tmp_path):
    path = tmp_path / "learning_constraints.jsonl"
    path.write_text(
        '{"id":"x","created_clock_ns":1,"session_id":"s","drive_id":"d",'
        '"source_ticket_id":"","kind":"crop_band","target":"scorebug_crops",'
        '"payload":{"crop":[0.12,0.88,0.78,0.93]},"evidence":{},'
        '"frozen":false,"plane":"qoresence-observation"}\n',
        encoding="utf-8",
    )
    assert load_constraints(path) == []


# ── P2 code gate ───────────────────────────────────────────────────────────


def _green(uid: str) -> Unit:
    return Unit(unit_id=uid, kind="worker", scope="chapter", plane="qoresence-observation")


def test_evaluate_unit_green_path():
    r = evaluate_unit(_green("c1"))
    assert r.passed is True
    assert r.checks_run > 0
    assert r.errors == ()


def test_evaluate_unit_missing_mint():
    u = Unit(
        unit_id="bad",
        kind="worker",
        scope="chapter",
        claims_digits=True,
        source_ticket_id="",
    )
    r = evaluate_unit(u)
    assert r.passed is False
    assert "digits_without_seeing_path_mint" in r.errors


def test_evaluate_unit_batch_scope_rejected():
    r = evaluate_unit(Unit(unit_id="all", kind="worker", scope="drive"))
    assert r.passed is False
    assert "batch_scope" in r.errors
    r2 = evaluate_unit(Unit(unit_id="b", kind="worker", scope="batch"))
    assert "batch_scope" in r2.errors


def test_evaluate_unit_merge_count_gap():
    r = evaluate_unit(
        Unit(unit_id="m", kind="code", scope="chapter", expected_inputs=2, actual_inputs=1)
    )
    assert r.passed is False
    assert "merge_count_gap" in r.errors


def test_evaluate_unit_freeze_missing_kind_and_plane():
    r = evaluate_unit(Unit(unit_id="f", kind="worker", scope="chapter", is_freeze=True))
    assert "freeze_missing_kind" in r.errors
    r2 = evaluate_unit(Unit(unit_id="p", kind="worker", scope="chapter", plane="truth"))
    assert "plane_not_observation" in r2.errors


def test_empty_errors_without_checks_is_not_a_pass():
    hollow = GateResult(ok=True, errors=(), checks_run=0)
    assert hollow.passed is False


# ── P3 correction edge ─────────────────────────────────────────────────────


def test_correction_drops_one_unit_siblings_unchanged():
    a, b, c, d = _green("a"), _green("b"), _green("c"), _green("d")
    d.scope = "batch"
    out = correct_units([a, b, c, d])
    assert [u.unit_id for u in out.kept] == ["a", "b", "c"]
    assert out.kept[0] is a and out.kept[1] is b and out.kept[2] is c
    assert len(out.receipts) == 1
    assert out.receipts[0].unit_id == "d"
    assert out.receipts[0].correction_exhausted is True
    assert out.receipts[0].attempts == RETRY_CAP


def test_correction_third_fail_sets_exhausted_no_digits():
    bad = Unit(unit_id="x", kind="worker", scope="chapter", claims_digits=True)
    out = correct_units([bad])
    assert out.kept == ()
    assert out.receipts[0].correction_exhausted is True
    assert out.receipts[0].attempts == 3
    assert "digits_without_seeing_path_mint" in out.receipts[0].errors
    assert "21-14" not in str(out.receipts[0])


# ── P4 learning edge / splitter ────────────────────────────────────────────


def test_flag_off_by_default_and_play_does_not_enable():
    assert enabled() is False
    assert RetinaUnifiedConfig().learning_edge is False
    src = __import__("pathlib").Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "learning_edge=True" not in src
    assert "learning_edge=_tp" not in src


def test_flag_off_drivegraph_summary_matches_baseline():
    g = DriveGraph.from_events("td", _td_events())
    g.started_ns = 0
    baseline = g.summary()
    nodes = g.ranked_chapter_nodes(k=3)
    kept, lite = split_chapter_units(g, k=3)
    assert [n.node_id for n in kept] == [n.node_id for n in nodes]
    assert lite.receipts == ()
    assert DriveGraph.from_events("td", _td_events()).summary()["phase"] == baseline["phase"]
    assert baseline["phase"] == DriveGraph.from_events("td", _td_events()).summary()["phase"]
    g2 = DriveGraph.from_events("td", _td_events())
    g2.started_ns = 0
    assert g2.summary() == baseline


def test_flag_off_does_not_read_or_write_constraints(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_LEARNING_CONSTRAINTS_PATH", str(tmp_path / "c.jsonl"))
    path = tmp_path / "c.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    assert load_applicable("ncaa_football_27", path=path) == []
    ticket = _ticket()
    assert maybe_record_on_resolve(ticket=ticket, crop=list(CFB_PRIMARY_SCOREBUG), path=path) is None
    # original file unchanged (still one empty-json line, no constraint record)
    body = path.read_text(encoding="utf-8")
    assert "crop_band" not in body
    assert overlay_crops("ncaa_football_27", CFB_SCOREBUG_CROPS) is None
    assert closeout_applied() is None


def test_flag_on_crop_constraint_changes_crop_only(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_NAME, "1")
    monkeypatch.setenv("QORESENCE_LEARNING_CONSTRAINTS_PATH", str(tmp_path / "c.jsonl"))
    ticket = _ticket()
    new_crop = [0.05, 0.95, 0.80, 0.94]
    c = from_accepted_confirm(
        ticket,
        kind="crop_band",
        payload={"crop": new_crop, "profile": "ncaa_football_27"},
    )
    assert c is not None
    append_constraint(c, path=tmp_path / "c.jsonl")
    over = scorebug_crops_for_profile("ncaa_football_27")
    assert over[0] == tuple(new_crop)
    assert over[0] != CFB_PRIMARY_SCOREBUG
    madden = scorebug_crops_for_profile("madden_27")
    assert madden[0] == MADDEN_PRIMARY_SCOREBUG


def test_flag_on_confirmed_play_still_dominates_t0_board(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "1")
    g = DriveGraph.from_events("td", _td_events())
    g.started_ns = 0
    ranked = g.ranked_chapter_nodes(k=3)
    labels = [n.label.lower() for n in ranked]
    assert any(
        "touchdown" in x or n.kind == "confirm_score" for n, x in zip(ranked, labels, strict=True)
    )
    kept, _ = split_chapter_units(g, k=3)
    assert any(n.kind == "confirm_score" or "touchdown" in n.label.lower() for n in kept)


def test_ticketless_constraint_ignored_on_apply(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "1")
    ghost = LearningConstraint(
        id="ghost",
        created_clock_ns=1,
        session_id="s",
        drive_id="d",
        source_ticket_id="",
        kind="crop_band",
        target="scorebug_crops",
        payload={"crop": [0.0, 1.0, 0.0, 1.0]},
        frozen=False,
        plane="qoresence-observation",
    )
    base = SplitterInputs(profile="ncaa_football_27", crops=CFB_SCOREBUG_CROPS)
    out = apply_constraints(base, [ghost])
    assert out.crops == CFB_SCOREBUG_CROPS
    assert out.applied_ids == ()


# ── P5 closed lanes ────────────────────────────────────────────────────────


def test_high_climax_without_ticket_cannot_publish_wrap_or_digits():
    snap = closed_lane_snapshot(climax=0.99, source_ticket_id="", proposed_text="locked 21-14")
    assert snap["publish"] is False
    assert snap["wrap_qortroller_truth"] is False
    assert snap["serialize_digits"] is False
    assert snap["dest_denied"] is True
    assert "21-14" not in snap["stripped"]
    assert lane_allows("crop_band", climax=0.99, source_ticket_id="abc") is True
    assert lane_allows("publish", climax=0.99, source_ticket_id="abc") is False
