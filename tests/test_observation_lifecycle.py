import json
from pathlib import Path
from types import SimpleNamespace

from qoresence.compose.clock_notary.envelope import Tick, envelope_from_recap
from qoresence.observation.lifecycle import normalize_visual, reduce_observation
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


def bus_visual_payload(clock_ns: int, evidence_id: str, phase: str) -> dict:
    return {
        "game_category": "football",
        "game_state": "gameplay",
        "visual_phase": phase,
        "event_id": evidence_id,
        "observation_tick": Tick(
            clock_ns=clock_ns,
            frame_seq=clock_ns // 1_000_000_000,
            ticket_id=None,
            ticket_kind=None,
            hid_edge=None,
            score_digits=None,
            evidence_id=evidence_id,
        ).as_commit_triple(),
    }


class Bus:
    def __init__(self):
        self.events = []

    def emit_raw(self, *args, **kwargs):
        self.events.append(args)


def test_replay_and_revisions_do_not_mutate_previous():
    stream = [
        ev(1),
        ev(2),
        ev(3, "huddle_offense"),
        ev(
            4, "huddle_offense", score_claim=scoreboard_claim()
        ),
    ]

    def replay():
        state = None
        history = []
        for event in stream:
            state = reduce_observation(state, event)
            history.append(state)
        return history

    history = replay()
    assert history == replay()
    assert [r["state"] for r in history] == ["candidate", "tracking", "partial", "confirmed"]
    assert history[0]["claims"] == []
    assert history[-1]["outcome"] is None
    assert history[-1]["input_availability"] == "not_on_this_host"
    assert len({r["observation_id"] for r in history}) == 1


def test_duplicate_and_late_evidence_do_not_reopen():
    state = reduce_observation(None, ev(1))
    state = reduce_observation(state, ev(3, "huddle_offense"))
    assert reduce_observation(state, ev(2)) == state
    assert reduce_observation(state, ev(3, "huddle_offense")) == state
    assert reduce_observation(state, ev(4))["observation_id"] != state["observation_id"]


def test_late_clip_completion_updates_original_without_rewinding_clock(tmp_path):
    runtime = ObservationRuntime(Bus(), tmp_path / "journal")
    runtime.process(ev(1))
    runtime.process(ev(2, "huddle_offense"))
    old = runtime.current["observation_id"]
    runtime.process(ev(3))
    current = runtime.current["observation_id"]
    clip_eid = old + f":clip:r{runtime.records[old]['revision']}"
    runtime.process(
        {
            "kind": "clip",
            "session_id": "session",
            "observation_id": old,
            "evidence_id": clip_eid,
            "tick": Tick(
                clock_ns=2_000_000_000,
                frame_seq=0,
                ticket_id=None,
                ticket_kind=None,
                hid_edge=None,
                score_digits=None,
                evidence_id=clip_eid,
            ).as_commit_triple(),
            "clip": {"status": "failed"},
        }
    )
    assert runtime.current["observation_id"] == current
    assert runtime.records[old]["clip"]["status"] == "failed"
    assert old != current


def test_gap_refuses_confirmation():
    state = reduce_observation(None, ev(1))
    state = reduce_observation(state, dict(ev(2), kind="gap"))
    state = reduce_observation(state, ev(3, "huddle_offense", score_claim={"home": 7, "away": 3}))
    assert state["state"] == "unresolved"
    assert state["claims"] == []


def test_stale_confirmation_not_applied():
    state = reduce_observation(None, ev(1))
    state = reduce_observation(state, ev(2, "huddle_offense"))
    state = reduce_observation(state, ev(12, "huddle_offense", score_claim={"home": 7, "away": 3}))
    assert state["claims"] == []


def test_callback_only_enqueues_and_overflow_is_visible(tmp_path):
    runtime = ObservationRuntime(Bus(), tmp_path / "journal", queue_size=1)
    event = SimpleNamespace(type="visual_context")
    runtime._on_event(event)
    runtime._on_event(event)
    assert runtime.dropped == 1
    assert not runtime.journal.exists()
    assert not runtime.bus.events


def test_journal_is_replayable_and_fanout_is_outside_lock(tmp_path):
    runtime = ObservationRuntime(Bus(), tmp_path / "journal")

    def fanout(*args, **kwargs):
        assert runtime.lock.acquire(blocking=False)
        runtime.lock.release()

    runtime.bus.emit_raw = fanout
    runtime.process(ev(1))
    runtime.process(ev(2, "huddle_offense"))
    state = None
    for line in runtime.journal.read_text().splitlines():
        item = json.loads(line)
        state = reduce_observation(state, item["evidence"], item["policy_version"])
        assert state == item["record"]


def test_storage_failure_is_visible(tmp_path):
    runtime = ObservationRuntime(Bus(), tmp_path)
    runtime.process(ev(1))
    assert runtime.snapshot()["persistence_error"]


def test_outcome_heuristics_are_not_normalized_as_visual_claims():
    assert normalize_visual({"payload": {"game_category": "shooter"}}) is None


def test_missing_ticket_fails_closed():
    from qoresence.observation.lifecycle import freeze_score_claim

    assert freeze_score_claim({"football": {"home_score": 7, "away_score": 3}}, 1) is None


def test_visual_emission_stamps_the_same_evidence_tick_on_the_bus(monkeypatch):
    from qoresence.lobes.visual import VisualRuntime
    from qoresence.vision.visual_context import GameCategory, GameState, VisualContext

    class CapturingBus:
        session_id = "session"

        def __init__(self):
            self.calls = []

        def emit_raw(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    bus = CapturingBus()
    runtime = VisualRuntime.__new__(VisualRuntime)
    runtime.bus = bus
    runtime.session_head_ns = 1
    runtime._presence_callback = None
    monkeypatch.setenv("QORESENCE_OBSERVATIONS", "1")
    runtime._emit_visual_context(
        VisualContext(
            game_state=GameState.GAMEPLAY,
            game_category=GameCategory.FOOTBALL,
            details={"visual_phase": "running"},
        ),
        frame_seq=9,
    )
    payload = bus.calls[0][1]["payload"]
    assert payload["event_id"] == payload["observation_tick"]["evidence_id"]
    assert payload["observation_tick"]["frame_seq"] == 9
    normalized = normalize_visual(
        {
            "session_id": "session",
            "clock_ns": bus.calls[0][1]["clock_ns_override"],
            "payload": payload,
        }
    )
    assert normalized and normalized["evidence_id"] == payload["event_id"]


def test_recap_export_carries_one_replayable_lifecycle_sidecar(tmp_path):
    runtime = ObservationRuntime(Bus(), tmp_path / "observations.jsonl")
    runtime.process(ev(1))
    runtime.process(ev(2, "huddle_offense"))
    observations = runtime.snapshot(include_journal=True)
    body = envelope_from_recap(
        {"session_id": "session", "ticks": [], "observations": observations}
    ).to_dict()
    assert body["schema"] == "qoresence.observation-envelope.v0"
    assert body["sidecar_hashes"]["observations"].startswith("sha256:")
    assert body["extras"]["observations"]["records"][0]["observation_id"] == "1"
    assert all("observation_id" in tick and "revision" in tick for tick in body["ticks"])
    assert body["ticks"][0]["evidence_id"] == "1"


def test_overlay_uses_observation_identity_without_play_confirmation_wording():
    html = Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "observations.html"
    source = html.read_text(encoding="utf-8")
    assert "record.observation_id" in source
    assert "scoreboard qualified" in source
    assert "candidate football play" in source


def test_ticket_must_match_score_and_be_fresh(monkeypatch):
    from qoresence.observation.lifecycle import freeze_score_claim
    from qoresence.vision.confirm_ticket import ConfirmTicket

    ticket = ConfirmTicket("test", "session", 1_000_000_000, 7, 3, crop_hash="crop")
    monkeypatch.setattr(
        "qoresence.vision.confirm_ticket.get_ticket_book",
        lambda: SimpleNamespace(get=lambda _: ticket),
    )
    context = {
        "confirm_ticket_id": "test",
        "score_vlm_locked": True,
        "football": {"home_score": 7, "away_score": 3},
    }
    assert freeze_score_claim(context, 2_000_000_000)["qualification"]["licensed"]
    assert freeze_score_claim(context, 10_000_000_000) is None
    assert freeze_score_claim(context, 500_000_000) is None
    context["football"]["home_score"] = 14
    assert freeze_score_claim(context, 2_000_000_000) is None


def test_live_worker_drains_clip_failure_without_blocking_bus(tmp_path, monkeypatch):
    import threading
    from qoresence.core import RetinaEventBus
    from qoresence.core.types import SourceLobe

    monkeypatch.setenv("QORESENCE_OBSERVATIONS", "1")
    bus = RetinaEventBus(session_id="session", enable_ws=False)
    started, release = threading.Event(), threading.Event()

    def export(record):
        started.set()
        assert release.wait(2)
        raise OSError("synthetic encode failure")

    runtime = ObservationRuntime(bus, tmp_path / "journal", export=export).start()
    try:
        for n, phase in [(1, "running"), (2, "huddle_offense")]:
            bus.emit_raw(
                SourceLobe.VISUAL,
                "visual_context",
                bus_visual_payload(n * 1_000_000_000, str(n), phase),
                clock_ns_override=n * 1_000_000_000,
            )
        assert started.wait(2)
        # Export is deliberately stalled; the callback still returns immediately.
        bus.emit_raw(
            SourceLobe.VISUAL,
            "visual_context",
            {"game_category": "shooter"},
            clock_ns_override=3_000_000_000,
        )
    finally:
        release.set()
        runtime.stop()
    assert not runtime.worker.is_alive()
    assert not runtime.clip_worker.is_alive()
    assert runtime.current["clip"]["status"] == "failed"


def test_shared_api_and_overlay(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    import qoresence.observation.runtime as module
    from qoresence.deck.server import create_app

    runtime = ObservationRuntime(Bus(), tmp_path / "journal")
    runtime.process(ev(1))
    monkeypatch.setattr(module, "_runtime", runtime)
    client = TestClient(create_app())
    assert (
        client.get("/api/observations").json()["records"][0]["observation_id"]
        == runtime.current["observation_id"]
    )
    assert client.get("/observations.html?overlay=1").status_code == 200
    from qoresence.agents.agent_glass import AgentGlass

    assert AgentGlass().snapshot()["observations"]["records"] == runtime.snapshot()["records"]


def test_historical_clip_refuses_missing_interval(tmp_path):
    from qoresence.vision.clip_buffer import HdmiClipBuffer

    buffer = HdmiClipBuffer(out_dir=tmp_path)
    buffer._frames.extend([(2.0, b"", 10, 10, 1), (3.0, b"", 10, 10, 2)])
    assert buffer.export(start_ns=1_000_000_000, end_ns=3_000_000_000) is None
    assert buffer.export(start_ns=2_000_000_000, end_ns=4_000_000_000) is None
    assert not list(tmp_path.iterdir())


def test_historical_clip_encodes_requested_window(tmp_path, monkeypatch):
    import shutil
    import cv2
    import numpy as np
    import pytest
    import qoresence.vision.clip_buffer as module

    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg required for browser-playable interval export")
    buffer = module.HdmiClipBuffer(out_dir=tmp_path)
    for index in range(41):
        frame = np.full((64, 64, 3), index * 5, dtype=np.uint8)
        _, jpeg = cv2.imencode(".jpg", frame)
        buffer._frames.append((1 + index / 10, jpeg.tobytes(), 64, 64, index))
    windows = []
    monkeypatch.setattr(
        module,
        "_write_coupling_sidecar",
        lambda path, snapshot: windows.append([row[0] for row in snapshot]),
    )
    result = buffer.export(start_ns=2_000_000_000, end_ns=3_000_000_000)
    assert result and result.size_bytes > 0
    assert windows[0][0] == 2 and windows[0][-1] == 3
    assert result.frames == 11
