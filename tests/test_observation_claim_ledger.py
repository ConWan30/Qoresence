import pytest

from qoresence.compose.clock_notary.envelope import Tick
from qoresence.observation.claims import (
    build_interpretation_claim,
    build_suggestion_claim,
    validate_claim,
)
from qoresence.observation.lifecycle import reduce_observation


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
    return dict(
        kind="visual",
        session_id="session",
        evidence_id=evidence_id,
        tick=tick,
        phase=phase,
        game_state="gameplay",
        **extra,
    )


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


def test_interpretation_requires_observation_refs():
    event = ev(1)
    with pytest.raises(ValueError, match="observation supporting refs"):
        build_interpretation_claim(
            statement="Resembles coverage",
            supporting_refs=[],
            observation_id="1",
            event=event,
            disposition="accepted",
            disposition_reason="test",
        )


def test_suggestion_cannot_invent_causation():
    with pytest.raises(ValueError, match="causation"):
        build_suggestion_claim(
            statement="You panic threw because you choked",
            supporting_refs=[{"type": "evidence", "evidence_id": "1"}],
            observation_id="1",
            sample_size=2,
            uncertainty="high",
            disposition="withheld",
            disposition_reason="test",
        )


def test_confirmed_record_has_observation_and_interpretation_claims():
    state = None
    for event in [
        ev(1),
        ev(2),
        ev(3, "huddle_offense"),
        ev(4, "huddle_offense", score_claim=scoreboard_claim()),
    ]:
        state = reduce_observation(state, event)
    kinds = {claim["kind"] for claim in state["ledger"]}
    assert "observation" in kinds
    assert "interpretation" in kinds
    observation = next(c for c in state["ledger"] if c["kind"] == "observation")
    assert observation["supporting_refs"][0]["evidence_id"] == "4"
    validate_claim(observation)


def test_partial_record_has_withheld_suggestion_not_causation():
    state = reduce_observation(None, ev(1))
    state = reduce_observation(state, ev(2, "huddle_offense"))
    suggestion = next(c for c in state["ledger"] if c["kind"] == "suggestion")
    assert suggestion["disposition"] == "withheld"
    assert suggestion["sample_size"] == 0
    validate_claim(suggestion)


def test_observations_review_renders_clickable_ledger():
    html = (
        pytest.importorskip("pathlib").Path(__file__).resolve().parents[1]
        / "qoresence"
        / "deck"
        / "observations.html"
    ).read_text(encoding="utf-8")
    assert "renderLedger" in html
    assert "claim-link" in html
    assert "jumpToEvidence" in html
    assert "evidence-dump" in html
