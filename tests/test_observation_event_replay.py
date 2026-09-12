import json
from pathlib import Path

from qoresence.compose.clock_notary.envelope import Tick
from qoresence.observation.lifecycle import (
    DETECTOR_SCHEMA,
    JOURNAL_SCHEMA,
    POLICY,
    freeze_detector_output,
    journal_bytes,
    load_journal_lines,
    pack_journal_row,
    parse_journal_row,
    reduce_observation,
    replay_journal,
)
from qoresence.observation.replay import main as replay_main
from qoresence.observation.runtime import ObservationRuntime


def ev(n, phase="running", **extra):
    evidence_id = str(n)
    claim = extra.get("score_claim") if isinstance(extra.get("score_claim"), dict) else None
    ticket = claim.get("ticket") if claim else {}
    if not isinstance(ticket, dict):
        ticket = {}
    tick = Tick(
        clock_ns=n * 1_000_000_000,
        frame_seq=n,
        ticket_id=ticket.get("ticket_id") if claim else None,
        ticket_kind="confirm" if claim else None,
        hid_edge=None,
        score_digits=f'{claim["home"]}-{claim["away"]}' if claim else None,
        score_vlm_locked=bool(claim),
        evidence_id=evidence_id,
    ).as_commit_triple()
    detector_output = extra.pop("detector_output", None)
    evidence = dict(
        kind="visual",
        session_id="session",
        evidence_id=evidence_id,
        tick=tick,
        phase=phase,
        game_state="gameplay",
        **extra,
    )
    if detector_output is not None:
        evidence["detector_output"] = detector_output
    return evidence


def scoreboard_claim() -> dict:
    ticket = {
        "ticket_id": "ticket-1",
        "session_id": "session",
        "clock_ns": 3_000_000_000,
        "home_score": 7,
        "away_score": 3,
        "frame_seq": 3,
        "crop_hash": "crop",
    }
    return {
        "kind": "historical_scoreboard",
        "home": 7,
        "away": 3,
        "ticket": ticket,
        "qualification": {"licensed": True},
    }


class Bus:
    def emit_raw(self, *args, **kwargs):
        return None


def build_journal_rows():
    rows = []
    state = None
    stream = [
        ev(1),
        ev(2),
        ev(3, "huddle_offense"),
        ev(4, "huddle_offense", score_claim=scoreboard_claim()),
    ]
    for evidence in stream:
        state = reduce_observation(state, evidence)
        rows.append(pack_journal_row(evidence, state))
    return rows


def test_pack_journal_row_has_versioned_schema():
    rows = build_journal_rows()
    assert rows[0]["schema_version"] == JOURNAL_SCHEMA
    assert rows[0]["policy_version"] == POLICY
    parse_journal_row(rows[0])


def test_journal_bytes_are_byte_stable():
    rows = build_journal_rows()
    first = journal_bytes(rows)
    second = journal_bytes(rows)
    assert first == second
    assert first == journal_bytes(load_journal_lines(first.decode("utf-8")))


def test_replay_journal_revision_parity():
    rows = build_journal_rows()
    records = replay_journal(rows, session_id="session")
    assert len(records) == 1
    assert records[0]["state"] == "confirmed"
    assert records[0]["revision"] == 4


def test_out_of_order_rows_do_not_reopen_on_replay():
    rows = build_journal_rows()
    # Swap two middle revisions; replay must fail closed.
    rows[1], rows[2] = rows[2], rows[1]
    try:
        replay_journal(rows, session_id="session")
        raise AssertionError("expected replay mismatch")
    except ValueError as exc:
        assert "replay mismatch" in str(exc)


def test_late_evidence_ignored_without_reopening():
    state = reduce_observation(None, ev(1))
    state = reduce_observation(state, ev(3, "huddle_offense"))
    assert reduce_observation(state, ev(2)) == state
    rows = [
        pack_journal_row(ev(1), reduce_observation(None, ev(1))),
        pack_journal_row(ev(3, "huddle_offense"), state),
    ]
    records = replay_journal(rows, session_id="session")
    assert records[0]["state"] == "partial"


def test_detector_output_preferred_over_phase_field():
    frozen = {
        "schema_version": DETECTOR_SCHEMA,
        "visual_phase": "huddle_offense",
        "game_state": "gameplay",
    }
    state = reduce_observation(None, ev(1))
    closed = reduce_observation(
        state,
        ev(2, phase="running", detector_output=frozen),
    )
    assert closed["state"] == "partial"
    assert closed["end_ns"] == 2_000_000_000


def test_freeze_detector_output_schema():
    payload = {
        "visual_phase": "running",
        "game_state": "gameplay",
        "game_category": "football",
        "model": "quicksilver",
        "frame_hash": "abc",
        "visual_confidence": 0.9,
        "football": {"home_score": 7, "away_score": 3},
    }
    frozen = freeze_detector_output(payload)
    assert frozen["schema_version"] == DETECTOR_SCHEMA
    assert frozen["visual_phase"] == "running"
    assert frozen["home_score"] == 7


def test_runtime_writes_versioned_journal(tmp_path):
    runtime = ObservationRuntime(Bus(), tmp_path / "journal")
    runtime.process(ev(1))
    runtime.process(ev(2, "huddle_offense"))
    row = json.loads(runtime.journal.read_text().splitlines()[0])
    assert row["schema_version"] == JOURNAL_SCHEMA
    replay_journal(load_journal_lines(runtime.journal.read_text()), session_id="session")


def test_replay_cli_ok(tmp_path):
    journal = tmp_path / "observations.jsonl"
    journal.write_bytes(journal_bytes(build_journal_rows()))
    assert replay_main([str(journal)]) == 0


def test_replay_cli_reports_mismatch(tmp_path):
    journal = tmp_path / "observations.jsonl"
    rows = build_journal_rows()
    rows[1], rows[2] = rows[2], rows[1]
    journal.write_bytes(journal_bytes(rows))
    assert replay_main([str(journal)]) == 1


def test_visual_event_replay_hook(monkeypatch):
    from qoresence.lobes.visual import VisualRuntime
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    class CapturingBus:
        session_id = "session"

        def __init__(self):
            self.calls = []

        def emit_raw(self, *args, **kwargs):
            self.calls.append(kwargs)

    bus = CapturingBus()
    runtime = VisualRuntime.__new__(VisualRuntime)
    runtime.bus = bus
    runtime.session_head_ns = 1
    runtime._presence_callback = None
    monkeypatch.setenv("QORESENCE_EVENT_REPLAY", "1")
    runtime._emit_visual_context(
        VisualContext(
            game_state=GameState.GAMEPLAY,
            game_category=GameCategory.FOOTBALL,
            details={"visual_phase": "running"},
        ),
        frame_seq=4,
    )
    payload = bus.calls[0]["payload"]
    assert payload["observation_detector_output"]["schema_version"] == DETECTOR_SCHEMA
    assert payload["observation_detector_output"]["visual_phase"] == "running"


def test_unsupported_journal_schema_rejected():
    row = pack_journal_row(ev(1), reduce_observation(None, ev(1)))
    row["schema_version"] = "observation-journal-99"
    try:
        parse_journal_row(row)
        raise AssertionError("expected unsupported schema")
    except ValueError as exc:
        assert "unsupported" in str(exc)


def test_missing_schema_version_rejected():
    row = pack_journal_row(ev(1), reduce_observation(None, ev(1)))
    del row["schema_version"]
    try:
        parse_journal_row(row)
        raise AssertionError("expected missing schema to fail closed")
    except ValueError as exc:
        assert "schema" in str(exc).lower()


def test_freeze_detector_output_includes_raw_response():
    frozen = freeze_detector_output(
        {
            "visual_phase": "running",
            "game_state": "gameplay",
            "game_category": "football",
            "model": "quicksilver",
            "raw_response": "PHASE: running",
            "frame_hash": "abc",
            "football": {"home_score": 7, "away_score": 3},
        }
    )
    assert frozen["raw_response"] == "PHASE: running"


def test_observations_live_path_freezes_without_event_replay_env(monkeypatch):
    from qoresence.lobes.visual import VisualRuntime
    from qoresence.observation.lifecycle import normalize_visual
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    class CapturingBus:
        session_id = "session"

        def __init__(self):
            self.calls = []

        def emit_raw(self, *args, **kwargs):
            self.calls.append(kwargs)

    bus = CapturingBus()
    runtime = VisualRuntime.__new__(VisualRuntime)
    runtime.bus = bus
    runtime.session_head_ns = 1
    runtime._presence_callback = None
    monkeypatch.delenv("QORESENCE_EVENT_REPLAY", raising=False)
    monkeypatch.setenv("QORESENCE_OBSERVATIONS", "1")
    runtime._emit_visual_context(
        VisualContext(
            game_state=GameState.GAMEPLAY,
            game_category=GameCategory.FOOTBALL,
            details={"visual_phase": "running"},
            model="quicksilver",
            raw_response="PHASE: running",
        ),
        frame_seq=4,
    )
    payload = bus.calls[0]["payload"]
    assert payload["observation_detector_output"]["raw_response"] == "PHASE: running"
    evidence = normalize_visual(
        {
            "session_id": "session",
            "clock_ns": bus.calls[0]["clock_ns_override"],
            "payload": payload,
        }
    )
    assert evidence["detector_output"]["raw_response"] == "PHASE: running"


def test_replay_ignores_live_ticket_book(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("replay must not consult the live ticket book")

    monkeypatch.setattr("qoresence.vision.confirm_ticket.get_ticket_book", boom)
    rows = build_journal_rows()
    records = replay_journal(rows, session_id="session")
    assert records[0]["state"] == "confirmed"


FIXTURE = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "observation_replay_session.jsonl"
)


def test_committed_fixture_replays_to_stable_qualification():
    assert FIXTURE.is_file()
    rows = load_journal_lines(FIXTURE.read_text(encoding="utf-8"))
    assert rows
    assert {row["schema_version"] for row in rows} == {JOURNAL_SCHEMA}
    assert {row["policy_version"] for row in rows} == {POLICY}
    records = replay_journal(rows, session_id="session")
    states = [row["record"]["state"] for row in rows]
    assert "candidate" in states
    assert "confirmed" in states
    assert records[0]["outcome"] is None
    assert any(row["evidence"].get("detector_output") for row in rows)
    assert any(row["evidence"].get("score_claim") for row in rows)
    assert replay_main([str(FIXTURE)]) == 0
