"""OCCF connector bind — agent turn <-> observatory instant, fail-closed.

Locks in: bound/unbound/stale/denied correlation states, first-match sync
methods, closed deny reasons, the guest clock never stamping ``clock_ns``,
``licenses_digits`` False forever, binds written only through the unified
Jev ledger as ``pack="connector"`` (no orphan connector.jsonl), and the
default-OFF flag (--play does not enable).
"""

from __future__ import annotations

import pytest

from qoresence.core.unified_config import JevConnectorConfig, RetinaUnifiedConfig
from qoresence.observability.connector_bind import (
    DENY_REASONS,
    SYNC_METHODS,
    ConnectorBind,
    compose_bind,
    local_connector_answers,
    make_connector_from_config,
    note_agent_turn,
    reset_connector_bind,
)
from qoresence.observability.jev_ledger import (
    configure_jev_ledger,
    read_judgments,
    reset_jev_ledger,
)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_JEV_LEDGER", raising=False)
    monkeypatch.delenv("QORESENCE_JEV_CONNECTOR", raising=False)
    reset_jev_ledger()
    reset_connector_bind()
    yield
    reset_jev_ledger()
    reset_connector_bind()


def _engine(tmp_path, **kw):
    configure_jev_ledger(path=tmp_path / "jev_ledger.jsonl")
    # Deterministic classify: same local heuristic the engine falls back to,
    # injected so a live TypeSafe key on the box can't flake the suite.
    kw.setdefault(
        "ask_fn",
        lambda state: local_connector_answers(state.get("turn") or {}),
    )
    return ConnectorBind(JevConnectorConfig(enabled=True), **kw)


def _live_obs(**kw):
    obs = {
        "live": True,
        "has_frame": True,
        "clock_ns": 123_000_000,
        "frame_seq": 5000,
        "crop_hash": "crop:abc",
        "title_lock": "locked",
        "board_lock": "locked",
        "last_confirm": "present",
        "coupling": "present",
        "climax_ready": False,
        "witness_hash": "wit:5000",
    }
    obs.update(kw)
    return obs


# ── flags ────────────────────────────────────────────────────────────────


def test_default_off():
    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.jev_connector.enabled is False
    assert make_connector_from_config(config.jev_connector) is None


def test_env_enables(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_JEV_CONNECTOR", "1")
    cfg = RetinaUnifiedConfig.from_env()
    assert cfg.jev_connector.enabled is True
    eng = make_connector_from_config(cfg.jev_connector)
    assert eng is not None and eng.enabled is True


def test_play_does_not_enable():
    """--play alone must not flip the connector on (flag/env stay opt-in)."""
    from argparse import Namespace

    config = RetinaUnifiedConfig(session_id="t", session_head_ns=1)
    assert config.jev_connector.enabled is False
    args = Namespace(play=True, jev_connector=False)
    enabled = bool(
        getattr(args, "jev_connector", False) or config.jev_connector.enabled
    )
    assert enabled is False
    # --play wiring lives in main(); the flag stays explicit opt-in.
    assert JevConnectorConfig().enabled is False


def test_flag_and_env_registered():
    """--jev-connector / QORESENCE_JEV_CONNECTOR wired like --jev-ledger."""
    from pathlib import Path

    text = Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert '"--jev-connector"' in text
    assert "args, \"jev_connector\"" in text or "jev_connector" in text
    env_src = Path("qoresence/core/unified_config.py").read_text(encoding="utf-8")
    assert "QORESENCE_JEV_CONNECTOR" in env_src


# ── correlation states ───────────────────────────────────────────────────


def test_bound_live_pull(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {
            "brand": "muse",
            "turn_id": "t1",
            "asked_at_unix_ms": 9_999_999_999_999,
            "utterance": "what is happening right now?",
        },
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["schema"] == "qoresence.connector-bind.v0"
    assert bind["plane"] == "qoresence-observation"
    assert bind["correlation"]["state"] == "bound"
    assert bind["correlation"]["method"] == "live_pull"
    assert bind["correlation"]["witness_hash"] == "wit:5000"
    assert bind["observatory"]["clock_ns"] == 123_000_000
    assert bind["observatory"]["frame_seq"] == 5000
    assert bind["compose"]["action"] == "act"
    assert bind["licenses_digits"] is False


def test_unbound_no_session_frame(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory={"live": False, "has_frame": False},
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "unbound"
    assert bind["correlation"]["method"] == "none"
    assert bind["observatory"]["clock_ns"] == 0


def test_unbound_silent_chat(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "claude", "utterance": "hey, how are you?"},
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "unbound"
    assert bind["compose"]["action"] == "silent"


def test_stale_seq_out_of_window(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "that play", "echo_frame_seq": 100},
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "stale"
    assert bind["correlation"]["method"] == "seq_match"
    assert bind["correlation"]["same_seq"] is False
    assert bind["compose"]["action"] == "watch"
    assert bind["compose"]["speech"] == "boxes"


def test_stale_ticket_stale_drift(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory=_live_obs(ticket_stale=True, stale_class="crop_moved_on"),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "stale"
    assert bind["compose"]["speech"] == "boxes"


def test_denied_pad_not_on_this_plane(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "press the button and throw it deep"},
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "denied"
    assert bind["compose"]["action"] == "deny"
    assert bind["compose"]["deny_reason"] == "pad_not_on_this_plane"
    assert bind["compose"]["deny_reason"] in DENY_REASONS


def test_denied_mid_drive_publish(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "post this to twitch right now"},
        observatory=_live_obs(climax_ready=False),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "denied"
    assert bind["compose"]["deny_reason"] == "mid_drive"


def test_denied_preflight_off_plane_wrap(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "wrap it", "wrap_dest": "qortroller-truth"},
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "denied"
    assert bind["compose"]["deny_reason"] == "off_plane_wrap"
    assert bind["source"] == "preflight"


def test_denied_leave_localhost(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "send the clip to a public url"},
        observatory=_live_obs(lan_opt_in=False),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "denied"
    assert bind["compose"]["deny_reason"] == "localhost_only"


# ── sync methods ─────────────────────────────────────────────────────────


def test_seq_match_bound_in_window(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {
            "brand": "muse",
            "utterance": "back at that play",
            "echo_frame_seq": 4900,
        },
        observatory=_live_obs(seq_clocks={4900: 100_000_000}),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "bound"
    assert bind["correlation"]["method"] == "seq_match"
    assert bind["correlation"]["same_seq"] is False
    assert bind["observatory"]["frame_seq"] == 4900
    assert bind["observatory"]["clock_ns"] == 100_000_000


def test_chapter_id_bound(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "clip that drive", "chapter_id": "ch7"},
        observatory=_live_obs(
            chapters={"ch7": {"t0_clock_ns": 55_000_000, "frame_seq": 4200}}
        ),
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "bound"
    assert bind["correlation"]["method"] == "chapter_id"
    assert bind["observatory"]["clock_ns"] == 55_000_000


def test_recap_door_bound(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "pack this so I can take it with me"},
        observatory={
            "live": False,
            "has_frame": False,
            "recap_open": True,
            "recap_clock_commitment": 77_000_000,
        },
        session_id="s1",
    )
    assert bind["correlation"]["state"] == "bound"
    assert bind["correlation"]["method"] == "recap_door"
    assert bind["observatory"]["clock_ns"] == 77_000_000


def test_sync_method_first_match_order():
    assert SYNC_METHODS == (
        "live_pull",
        "seq_match",
        "chapter_id",
        "recap_door",
        "none",
    )
    assert "muse_vm_time" not in SYNC_METHODS
    assert "sync_glass_bind" not in SYNC_METHODS


# ── guest clock law ──────────────────────────────────────────────────────


def test_guest_clock_never_stamps_clock_ns(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "asked_at_unix_ms": 1_758_000_000_000, "utterance": "hi"},
        observatory={"live": False},
        session_id="s1",
    )
    assert bind["agent"]["asked_at_unix_ms"] == 1_758_000_000_000
    assert bind["observatory"]["clock_ns"] == 0
    assert bind["observatory"]["clock_ns"] != bind["agent"]["asked_at_unix_ms"]


# ── ledger-only writes ───────────────────────────────────────────────────


def test_ledger_receives_pack_connector(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory=_live_obs(),
        session_id="s1",
    )
    (row,) = list(read_judgments(tmp_path / "jev_ledger.jsonl"))
    assert row["schema"] == "qoresence.jev.ledger.v0"
    assert row["plane"] == "qoresence-observation"
    assert row["pack"] == "connector"
    assert row["clock_ns"] == 123_000_000
    assert row["frame_seq"] == 5000
    assert row["licenses_digits"] is False
    verdict = row["verdict"]
    assert verdict["schema"] == "qoresence.connector-bind.v0"
    assert verdict["bind_id"] == bind["bind_id"]
    assert verdict["licenses_digits"] is False


def test_denied_turn_also_noted(tmp_path):
    eng = _engine(tmp_path)
    eng.bind_turn(
        {"brand": "grok", "utterance": "press A and make him catch it"},
        observatory=_live_obs(),
        session_id="s1",
    )
    (row,) = list(read_judgments(tmp_path / "jev_ledger.jsonl"))
    assert row["pack"] == "connector"
    assert row["verdict"]["correlation"]["state"] == "denied"
    assert row["verdict"]["compose"]["deny_reason"] == "pad_not_on_this_plane"


def test_no_orphan_connector_jsonl(tmp_path):
    eng = _engine(tmp_path)
    for turn in (
        {"brand": "muse", "utterance": "what's the score?"},
        {"brand": "muse", "utterance": "press the button"},
        {"brand": "muse", "utterance": "hello"},
    ):
        eng.bind_turn(turn, observatory=_live_obs(), session_id="s1")
    names = {p.name for p in tmp_path.rglob("*") if p.is_file()}
    assert names == {"jev_ledger.jsonl"}
    rows = list(read_judgments(tmp_path / "jev_ledger.jsonl"))
    assert len(rows) == 3
    assert all(r["pack"] == "connector" for r in rows)


def test_no_session_id_no_write(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory=_live_obs(),
    )
    assert bind is not None
    assert not (tmp_path / "jev_ledger.jsonl").exists()


def test_connector_off_writes_nothing(tmp_path):
    configure_jev_ledger(enabled=True, path=tmp_path / "jev_ledger.jsonl")
    eng = ConnectorBind(JevConnectorConfig(enabled=False))
    assert (
        eng.bind_turn(
            {"brand": "muse", "utterance": "score?"},
            observatory=_live_obs(),
            session_id="s1",
        )
        is None
    )
    assert note_agent_turn(
        {"brand": "muse", "utterance": "score?"}, session_id="s1"
    ) is None


# ── speech / honesty ─────────────────────────────────────────────────────


def test_digit_ask_confirm_present_speech_tokens(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory=_live_obs(last_confirm="present"),
        session_id="s1",
    )
    assert bind["compose"]["speech"] == "confirm_tokens"


def test_digit_ask_no_confirm_speech_boxes(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory=_live_obs(last_confirm="absent"),
        session_id="s1",
    )
    assert bind["compose"]["speech"] == "boxes"


def test_asserted_score_never_serialized(tmp_path):
    """A Muse '21-17' in the utterance never lands on the row as digits."""
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "it's 21-17, what's the score?"},
        observatory=_live_obs(last_confirm="absent"),
        session_id="s1",
    )
    assert bind["compose"]["speech"] == "boxes"
    assert bind["intent"]["nouls"]["asserts_a_score"] >= 0.5
    assert "21-17" not in str(bind)
    assert "21" not in str(bind["observatory"])


def test_licenses_digits_false_everywhere(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "what's the score?"},
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["licenses_digits"] is False
    assert eng.stats()["licenses_digits"] is False
    (row,) = list(read_judgments(tmp_path / "jev_ledger.jsonl"))
    assert row["licenses_digits"] is False
    assert row["verdict"]["licenses_digits"] is False


def test_no_score_integers_on_bind(tmp_path):
    eng = _engine(tmp_path)
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "score check"},
        observatory=_live_obs(home_score=21, away_score=17),
        session_id="s1",
    )
    obs = bind["observatory"]
    assert "home_score" not in obs and "away_score" not in obs
    assert "21" not in str(bind["intent"])


# ── heuristics / compose primitives ──────────────────────────────────────


def test_heuristic_pad_classify():
    out = local_connector_answers({"utterance": "press X and run the play"})
    assert out["tool"] == "refuse_actuator"
    assert out["nouls"]["asks_to_control_pad"] >= 0.6
    assert out["request_risk"] == 2
    assert out["source"] == "local_heuristic"


def test_heuristic_silent_classify():
    out = local_connector_answers({"utterance": "good morning"})
    assert out["tool"] == "silent"
    assert out["nouls"]["needs_a_tool_at_all"] < 0.3


def test_typesafe_shaped_answers_compose(tmp_path):
    """Injected typesafe-shape answers flow through code-owned compose."""
    eng = _engine(
        tmp_path,
        ask_fn=lambda state: {
            "tool": "get_observation",
            "tool_confidence": 0.9,
            "request_risk": 1,
            "nouls": {"asks_for_digits": 0.9, "needs_a_tool_at_all": 0.9},
            "source": "typesafe",
        },
    )
    bind = eng.bind_turn(
        {"brand": "muse", "utterance": "?"},
        observatory=_live_obs(),
        session_id="s1",
    )
    assert bind["source"] == "typesafe"
    assert bind["correlation"]["state"] == "bound"
    assert bind["compose"]["speech"] == "confirm_tokens"


def test_compose_closed_sets():
    bind = compose_bind(
        agent={"brand": "muse", "turn_id": "x", "asked_at_unix_ms": 1},
        intent={
            "tool": "get_observation",
            "tool_confidence": 0.9,
            "request_risk": 0,
            "nouls": {"needs_a_tool_at_all": 0.9},
        },
        observatory=_live_obs(),
        session_id="s",
        source="local_heuristic",
    )
    assert bind["correlation"]["state"] == "bound"
    assert bind["agent"]["brand"] == "muse"
    assert bind["source"] == "local_heuristic"
