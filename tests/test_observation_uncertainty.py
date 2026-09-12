from qoresence.compose.clock_notary.envelope import Tick
from qoresence.observation.lifecycle import reduce_observation
from qoresence.observation.uncertainty import (
    CHANNEL_INPUT,
    CHANNEL_OUTCOME,
    build_uncertainty_channels,
    collect_live_signals,
    initial_uncertainty_channels,
)


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


def test_initial_channels_abstain_unknown_capture():
    channels = initial_uncertainty_channels("not_on_this_host")
    assert channels[CHANNEL_INPUT] == {"status": "not_on_this_host"}
    assert channels["capture_freshness"] == {}
    assert "confidence" not in channels


def test_confirmed_scoreboard_keeps_input_unavailable():
    stream = [
        ev(1),
        ev(2),
        ev(3, "huddle_offense"),
        ev(4, "huddle_offense", score_claim=scoreboard_claim()),
    ]
    state = None
    for event in stream:
        state = reduce_observation(state, event)
    assert state["state"] == "confirmed"
    channels = state["uncertainty_channels"]
    assert channels[CHANNEL_INPUT]["status"] == "not_on_this_host"
    assert channels[CHANNEL_OUTCOME]["status"] == "scoreboard_qualified"
    assert channels[CHANNEL_OUTCOME]["licensed"] is True
    assert "confidence" not in state


def test_capture_freshness_from_frozen_inputs():
    channels = build_uncertainty_channels(
        input_availability="not_on_this_host",
        state="tracking",
        uncertainty_tags=[],
        channel_inputs={"video_age_s": 0.5},
    )
    assert channels["capture_freshness"]["status"] == "fresh"
    channels_stale = build_uncertainty_channels(
        input_availability="not_on_this_host",
        state="tracking",
        uncertainty_tags=[],
        channel_inputs={"video_age_s": 8.0},
    )
    assert channels_stale["capture_freshness"]["status"] == "stale"


def test_collect_live_signals_never_invents():
    signals = collect_live_signals()
    assert isinstance(signals, dict)
