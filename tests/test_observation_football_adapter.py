from qoresence.compose.clock_notary.envelope import Tick
from qoresence.observation.adapters import (
    FOOTBALL_ADAPTER,
    football_adapter_enabled,
    resolve_adapter,
)
from qoresence.observation.adapters.football.phases import ACTIVE_PHASES, BOUNDARY_PHASES
from qoresence.observation.lifecycle import normalize_visual, reduce_observation


def ev(n, phase="running", **extra):
    evidence_id = str(n)
    tick = Tick(
        clock_ns=n * 1_000_000_000,
        frame_seq=n,
        ticket_id=None,
        ticket_kind=None,
        hid_edge=None,
        score_digits=None,
        score_vlm_locked=False,
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


def bus_event(category: str, phase: str = "running", **extra) -> dict:
    evidence_id = "obs-test"
    clock_ns = 1_000_000_000
    tick = Tick(
        clock_ns=clock_ns,
        frame_seq=1,
        ticket_id=None,
        ticket_kind=None,
        hid_edge=None,
        score_digits=None,
        evidence_id=evidence_id,
    ).as_commit_triple()
    payload = {
        "game_category": category,
        "game_state": "gameplay",
        "visual_phase": phase,
        "event_id": evidence_id,
        "observation_tick": tick,
        **extra,
    }
    return {"session_id": "session", "clock_ns": clock_ns, "payload": payload}


def test_football_adapter_accepts_football_only():
    assert FOOTBALL_ADAPTER.accepts_category("football")
    assert not FOOTBALL_ADAPTER.accepts_category("shooter")
    assert not FOOTBALL_ADAPTER.accepts_category(None)


def test_snap_does_not_open_moment():
    assert not FOOTBALL_ADAPTER.should_open_moment("snap", None)
    assert FOOTBALL_ADAPTER.should_open_moment("running", None)


def test_huddle_closes_moment():
    assert FOOTBALL_ADAPTER.should_close_moment("huddle_offense", "gameplay")
    assert FOOTBALL_ADAPTER.should_close_moment("running", "menu")


def test_input_never_invents_presses():
    assert FOOTBALL_ADAPTER.input_availability(hid_observed=False) == "not_on_this_host"
    assert FOOTBALL_ADAPTER.input_availability(hid_observed=True) == "available"
    record = FOOTBALL_ADAPTER.new_candidate_record(ev(1), 1_000_000_000, "1", "football-observation-1")
    assert record["input_availability"] == "not_on_this_host"


def test_cfb_and_madden_blind_spots_differ():
    shared = set(FOOTBALL_ADAPTER.blind_spots("cfb_27"))
    madden = set(FOOTBALL_ADAPTER.blind_spots("madden_27"))
    assert "snap alone does not open a play interval" in shared
    assert any("CFB" in spot or "scorebug" in spot for spot in shared)
    assert any("challenge" in spot or "NFL" in spot for spot in madden)


def test_valid_transitions_cover_active_phases():
    transitions = FOOTBALL_ADAPTER.valid_transitions()
    for phase in ACTIVE_PHASES:
        assert phase in transitions or phase in BOUNDARY_PHASES


def test_non_football_abstains_from_normalize(monkeypatch):
    monkeypatch.delenv("QORESENCE_FOOTBALL_ADAPTER", raising=False)
    monkeypatch.delenv("QORESENCE_OBSERVATIONS", raising=False)
    assert resolve_adapter("shooter") is None
    assert normalize_visual(bus_event("shooter")) is None


def test_football_normalize_requires_adapter_enabled(monkeypatch):
    monkeypatch.delenv("QORESENCE_FOOTBALL_ADAPTER", raising=False)
    monkeypatch.delenv("QORESENCE_OBSERVATIONS", raising=False)
    assert normalize_visual(bus_event("football")) is None


def test_football_normalize_when_observations_on(monkeypatch):
    monkeypatch.setenv("QORESENCE_OBSERVATIONS", "1")
    evidence = normalize_visual(bus_event("football", profile="cfb_27"))
    assert evidence is not None
    assert evidence["game_category"] == "football"
    assert evidence["game_profile"] == "cfb_27"


def test_explicit_football_adapter_flag(monkeypatch):
    monkeypatch.delenv("QORESENCE_OBSERVATIONS", raising=False)
    monkeypatch.setenv("QORESENCE_FOOTBALL_ADAPTER", "1")
    assert football_adapter_enabled()
    assert resolve_adapter("football") is FOOTBALL_ADAPTER


def test_reduce_uses_adapter_boundaries():
    state = reduce_observation(None, ev(1, "running"))
    closed = reduce_observation(state, ev(2, "huddle_offense"))
    assert closed["state"] == "partial"
    assert closed["end_ns"] == 2_000_000_000


def test_unknown_phase_abstains_from_normalize(monkeypatch):
    monkeypatch.setenv("QORESENCE_OBSERVATIONS", "1")
    assert normalize_visual(bus_event("football", phase="touchdown_dance")) is None
