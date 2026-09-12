"""Lifecycle records ride the same clock_commitment as Recap ticks."""

from qoresence.compose.clock_notary.envelope import Tick, build_envelope, envelope_from_recap
from qoresence.observation.lifecycle import POLICY, reduce_observation
from qoresence.observation.present import glass_state, present_record, present_snapshot


def _tick(clock_ns: int, evidence_id: str, *, observation_id=None, revision=None):
    return Tick(
        clock_ns=clock_ns,
        frame_seq=clock_ns // 1_000_000_000,
        ticket_id=None,
        ticket_kind=None,
        hid_edge=None,
        score_digits=None,
        evidence_id=evidence_id,
        observation_id=observation_id,
        revision=revision,
    )


def _visual(n: int, phase="running"):
    eid = f"ev-{n}"
    return {
        "kind": "visual",
        "session_id": "session",
        "evidence_id": eid,
        "phase": phase,
        "game_state": "gameplay",
        "tick": _tick(n * 1_000_000_000, eid).as_commit_triple(),
    }


def test_glass_never_says_confirmed_play():
    assert glass_state("confirmed") == "scoreboard_qualified"
    shown = present_record({"state": "confirmed", "claims": [{"home": 7, "away": 3}]})
    assert shown["state"] == "confirmed"
    assert shown["glass_state"] == "scoreboard_qualified"
    assert "play outcome unassigned" in shown["glass_claim"]


def test_observation_id_is_first_evidence_id():
    first = reduce_observation(None, _visual(1))
    assert first["observation_id"] == "ev-1"
    tracking = reduce_observation(first, _visual(2))
    huddle = reduce_observation(tracking, _visual(3, "huddle_offense"))
    assert huddle["observation_id"] == "ev-1"
    assert huddle["state"] == "partial"
    assert huddle["outcome"] is None
    assert huddle["input_availability"] == "unavailable"


def test_tick_observation_ref_changes_commitment():
    bare = build_envelope(session_id="session", ticks=[_tick(1, "ev-1")])
    bound = build_envelope(
        session_id="session",
        ticks=[_tick(1, "ev-1", observation_id="ev-1", revision=1)],
    )
    assert bare.clock_commitment != bound.clock_commitment
    assert bound.ticks[0]["observation_id"] == "ev-1"
    assert bound.ticks[0]["revision"] == 1
    assert "observations" not in bound.sidecar_hashes


def test_recap_journal_hashes_as_observations_sidecar():
    first = reduce_observation(None, _visual(1))
    closed = reduce_observation(first, _visual(2, "huddle_offense"))
    row = {"policy_version": POLICY, "evidence": _visual(1), "record": first}
    # replay_journal walks every row; include both emitted revisions
    rows = [
        {"policy_version": POLICY, "evidence": _visual(1), "record": first},
        {"policy_version": POLICY, "evidence": _visual(2, "huddle_offense"), "record": closed},
    ]
    env = envelope_from_recap(
        {
            "session_id": "session",
            "ticks": [],
            "observations": {"enabled": True, "records": [closed], "journal": rows},
        }
    )
    assert "observations" in env.sidecar_hashes
    assert env.sidecar_hashes["observations"].startswith("sha256:")
    refs = [t for t in env.ticks if t.get("observation_id") == "ev-1"]
    assert refs
    assert refs[-1]["revision"] == closed["revision"]
    assert env.extras["observations"]["records"][-1]["observation_id"] == "ev-1"


def test_present_snapshot_keeps_journal_state():
    snap = present_snapshot({"records": [{"state": "confirmed", "claims": []}], "revisions": []})
    assert snap["records"][0]["state"] == "confirmed"
    assert snap["records"][0]["glass_state"] == "scoreboard_qualified"
