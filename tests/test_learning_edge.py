"""Learning-edge constraint schema (P1). Offline. No DriveGraph wiring."""

from __future__ import annotations

from qoresence.agents.learning_constraint import (
    CONSTRAINT_KINDS,
    DEFAULT_CONSTRAINT_LOG,
    OBSERVATION_PLANE,
    LearningConstraint,
    append_constraint,
    from_accepted_confirm,
    load_constraints,
    parse_constraint_record,
)
from qoresence.vision.confirm_ticket import mint_confirm_ticket
from qoresence.vision.scorebug_crops import CFB_PRIMARY_SCOREBUG


def _ticket(**kw):
    return mint_confirm_ticket(
        session_id=kw.get("session_id", "sess_p1"),
        clock_ns=kw.get("clock_ns", 1_000),
        home_score=kw.get("home_score", 21),
        away_score=kw.get("away_score", 14),
        source=kw.get("source", "deepseek"),
        frame_seq=kw.get("frame_seq", 12),
    )


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
    assert c.plane == OBSERVATION_PLANE
    assert c.target == "scorebug_crops"
    assert c.payload["crop"] == [0.12, 0.88, 0.78, 0.93]
    assert c.payload["profile"] == "ncaa_football_27"
    assert c.evidence["frame_seq"] == 12
    assert "home_score" not in c.payload
    assert "away_score" not in c.payload


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
    assert path.is_file()
    loaded = load_constraints(path)
    assert len(loaded) == 1
    got = loaded[0]
    assert got.id == c.id
    assert got.source_ticket_id == c.source_ticket_id
    assert got.kind == "crop_band"
    assert got.payload["crop"] == [0.12, 0.88, 0.78, 0.93]
    assert got.plane == OBSERVATION_PLANE
    again = parse_constraint_record(got.to_dict())
    assert again is not None
    assert again.id == c.id


def test_unknown_kind_rejected():
    ticket = _ticket()
    assert (
        from_accepted_confirm(
            ticket,
            kind="narrator",
            payload={"crop": list(CFB_PRIMARY_SCOREBUG)},
        )
        is None
    )
    assert (
        from_accepted_confirm(
            ticket,
            kind="play_advice",
            payload={"weight": 1.0, "node_kind": "arm"},
        )
        is None
    )


def test_frozen_field_write_rejected():
    ticket = _ticket()
    crop = list(CFB_PRIMARY_SCOREBUG)
    assert (
        from_accepted_confirm(
            ticket,
            kind="crop_band",
            target="qortroller-truth",
            payload={"crop": crop},
        )
        is None
    )
    assert (
        from_accepted_confirm(
            ticket,
            kind="crop_band",
            payload={"crop": crop, "wrap_dest": "qoresence-research"},
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
