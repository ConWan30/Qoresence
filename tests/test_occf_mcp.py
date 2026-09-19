"""OCCF slice 3 — pull-only observatory MCP tests.

Locks in: minimal tool catalog (get_observation + refuse_* only), default-OFF
opt-in gate, fail-closed blanks (board unlocked / no session / ledger off),
licenses_digits=False forever with score digits never echoed, localhost-only
pull, and no capture open.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import qoresence.mcp.occf as occf
import qoresence.mcp.server as mcp_server


def _rpc(msgs, env_extra=None):
    env = dict(os.environ)
    env.pop("QORESENCE_OCCF", None)
    if env_extra:
        env.update(env_extra)
    p = subprocess.Popen(
        [sys.executable, "-m", "qoresence.mcp.occf"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    inp = "\n".join(json.dumps(m) for m in msgs) + "\n"
    out, _ = p.communicate(inp, timeout=30)
    lines = [json.loads(x) for x in out.strip().splitlines() if x.strip()]
    p.terminate()
    return lines


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _call_payload(resp):
    return json.loads(resp["result"]["content"][0]["text"])


@pytest.fixture(autouse=True)
def _clean_occf(monkeypatch):
    monkeypatch.delenv("QORESENCE_OCCF", raising=False)
    monkeypatch.delenv("QORESENCE_JEV", raising=False)
    monkeypatch.delenv("QORESENCE_JEV_LEDGER", raising=False)
    monkeypatch.delenv("QORESENCE_JEV_LEDGER_PATH", raising=False)
    monkeypatch.setattr(occf, "_cli_enabled", False)
    yield
    from qoresence.observability.jev_ledger import reset_jev_ledger

    reset_jev_ledger()


@pytest.fixture
def _offline_glass(monkeypatch):
    """Force the pull path to fail closed — no live Deck needed."""
    monkeypatch.setattr(mcp_server, "_get_glass", lambda: None)
    monkeypatch.setattr(
        mcp_server,
        "_http_get",
        lambda path, token=None: {
            "ok": False,
            "error": "http_unreachable",
            "hint": f"forced offline for {path}",
        },
    )


LOCKED_SNAPSHOT = {
    "ok": True,
    "situation": {
        "game_profile": "madden_27",
        "title_claim": True,
        "title_hysteresis": "locked",
        "home_score": 14,
        "away_score": 10,
        "score_vlm_locked": True,
        "confirm_ticket_id": "c-1",
        "path": "confirm",
        "ticket_crop_hash": "crop-a",
        "crop_hash": "crop-a",
        "same_seq": True,
        "confirm_clock_ns": 1_000,
        "clock_ns": 2_000,
        "frame_seq": 12,
    },
    "video": {"has_frame": True},
    "coupling": {"phrase": "SNAP", "coupling": 0.6, "frame_seq": 12},
    "clock_ns": 2_000,
    "seq": 12,
}

UNLOCKED_SNAPSHOT = {
    "ok": True,
    "situation": {
        "game_profile": "madden_27",
        "title_claim": False,
        "title_hysteresis": "transitioning",
        "home_score": 21,
        "away_score": 7,
        "score_vlm_locked": False,
    },
    "video": {"has_frame": True, "age_s": 0.1, "seq": 9},
    "coupling": {"phrase": "SPRINT", "coupling": 0.4, "frame_seq": 9},
    "clock_ns": 1,
    "seq": 9,
}


def test_occf_initialize_names_observatory():
    resps = _rpc(
        [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}],
        env_extra={"QORESENCE_OCCF": "1"},
    )
    info = resps[0]["result"]
    assert info["serverInfo"]["name"] == "qoresence-observatory"
    assert info["occf"]["enabled"] is True
    assert info["occf"]["plane"] == "qoresence-observation"
    assert info["occf"]["licenses_digits"] is False


def test_occf_tools_list_minimal_catalog():
    resps = _rpc(
        [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}],
        env_extra={"QORESENCE_OCCF": "1"},
    )
    names = {t["name"] for t in resps[0]["result"]["tools"]}
    assert names == {"get_observation", "refuse_actuator", "refuse_mid_drive_publish"}
    for forbidden in (
        "get_timeline",
        "export_presence_pack",
        "search_clips",
        "get_frame",
        "civif_live",
        "wrap_observation",
        "subscribe_events",
        "send_pad_input",
    ):
        assert forbidden not in names


def test_occf_default_off_stdio():
    """No env / no flag → zero tools, every call fails closed."""
    resps = _rpc(
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "get_observation", "arguments": {}},
            },
        ]
    )
    assert resps[0]["result"]["occf"]["enabled"] is False
    assert resps[1]["result"]["tools"] == []
    call = resps[2]["result"]
    assert call["isError"] is True
    payload = _call_payload(resps[2])
    assert payload["ok"] is False
    assert payload["error"] == "occf_disabled"
    assert payload["licenses_digits"] is False


def test_occf_default_off_in_process(monkeypatch):
    assert occf.occf_enabled() is False
    resp = occf._handle_request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "refuse_actuator", "arguments": {}},
        }
    )
    payload = _call_payload(resp)
    assert payload["error"] == "occf_disabled"
    monkeypatch.setenv("QORESENCE_OCCF", "1")
    assert occf.occf_enabled() is True


def test_occf_play_does_not_enable():
    """--play must never flip the connector on — no cli wiring exists."""
    src = Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "QORESENCE_OCCF" not in src
    assert "--occf" not in src


def test_occf_fail_closed_when_unreachable(_offline_glass, monkeypatch):
    monkeypatch.setenv("QORESENCE_OCCF", "1")
    out = occf.handle_get_observation()
    assert out["ok"] is False
    assert out["plane"] == "qoresence-observation"
    assert out["licenses_digits"] is False
    assert out["score"] == {"claim": False, "home": None, "away": None}
    assert out["title"]["claim"] is False
    assert out["may_say"] == []
    assert out["must_not_invent"]


def test_occf_fail_closed_board_unlocked(monkeypatch):
    monkeypatch.setenv("QORESENCE_OCCF", "1")
    monkeypatch.setattr(
        mcp_server, "handle_get_snapshot", lambda: dict(UNLOCKED_SNAPSHOT)
    )
    out = occf.handle_get_observation()
    assert out["score"] == {"claim": False, "home": None, "away": None}
    assert "score_not_locked" in out["must_not_invent"]
    blob = json.dumps(out)
    assert "21-7" not in blob and "21–7" not in blob


def test_occf_never_echoes_score_digits(monkeypatch):
    """Locked board → claim token only; integers stay on the ConfirmTicket."""
    monkeypatch.setenv("QORESENCE_OCCF", "1")
    monkeypatch.setattr(
        mcp_server, "handle_get_snapshot", lambda: dict(LOCKED_SNAPSHOT)
    )
    out = occf.handle_get_observation()
    assert out["score"]["claim"] is True
    assert out["score"]["home"] is None
    assert out["score"]["away"] is None
    assert "score_digits_not_echoed" in out["must_not_invent"]
    blob = json.dumps(out)
    assert "14-10" not in blob and "14–10" not in blob
    assert not any("score 14" in str(line) for line in out["may_say"])
    # title / phrase tokens still flow — the read is not empty
    assert any("madden_27" in str(line) for line in out["may_say"])


def test_occf_licenses_digits_false_everywhere(monkeypatch):
    monkeypatch.setenv("QORESENCE_OCCF", "1")
    monkeypatch.setattr(
        mcp_server, "handle_get_snapshot", lambda: dict(LOCKED_SNAPSHOT)
    )
    for out in (
        occf.handle_get_observation(jev_tail=3),
        occf.handle_refuse_actuator(),
        occf.handle_refuse_mid_drive_publish(),
        occf._disabled_result(),
    ):
        for k, v in _keys(out):
            if k == "licenses_digits":
                assert v is False


def test_occf_scrub_forces_false():
    dirty = {
        "licenses_digits": True,
        "nested": {"licenses_digits": "yes", "rows": [{"licenses_digits": 1}]},
    }
    clean = occf.scrub_licenses_digits(dirty)
    for k, v in _keys(clean):
        if k == "licenses_digits":
            assert v is False


def test_occf_jev_tail_token_only(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_OCCF", "1")
    monkeypatch.setattr(
        mcp_server, "handle_get_snapshot", lambda: dict(UNLOCKED_SNAPSHOT)
    )
    from qoresence.observability.jev_ledger import JevLedger

    path = tmp_path / "jev_ledger.jsonl"
    ledger = JevLedger(path)
    try:
        ledger.append(
            "ticket_stale",
            {"action": "flag_stale", "source": "typesafe", "secret": "x"},
            clock_ns=123,
            frame_seq=7,
        )
        ledger.append("noul", {"hud_kind": "live_hud"})
    finally:
        ledger.close()

    # ledger off → fail-closed empty tail
    monkeypatch.delenv("QORESENCE_JEV_LEDGER", raising=False)
    out = occf.handle_get_observation(jev_tail=5)
    assert out["jev_tail"] == {"enabled": False, "rows": []}

    # ledger on → token rows, never the verdict body
    monkeypatch.setenv("QORESENCE_JEV_LEDGER", "1")
    monkeypatch.setenv("QORESENCE_JEV_LEDGER_PATH", str(path))
    out = occf.handle_get_observation(jev_tail=5)
    tail = out["jev_tail"]
    assert tail["enabled"] is True
    assert len(tail["rows"]) == 2
    row = tail["rows"][0]
    assert row["pack"] == "ticket_stale"
    assert row["action"] == "flag_stale"
    assert row["source"] == "typesafe"
    assert row["clock_ns"] == 123
    assert "verdict" not in row
    assert "secret" not in json.dumps(tail)
    assert row["licenses_digits"] is False


def test_occf_localhost_only(monkeypatch):
    """Pull path binds loopback; 0.0.0.0 is folded back to 127.0.0.1."""
    for var in ("QORESENCE_AGENT_GLASS_HOST", "QORESENCE_HOST", "QORESENCE_PORT"):
        monkeypatch.delenv(var, raising=False)
    host, _port = mcp_server._resolve_base()
    assert host == "127.0.0.1"
    monkeypatch.setenv("QORESENCE_HOST", "0.0.0.0")
    host, _port = mcp_server._resolve_base()
    assert host == "127.0.0.1"


def test_occf_no_capture_no_socket():
    """The connector never opens the card or binds a socket of its own."""
    src = Path("qoresence/mcp/occf.py").read_text(encoding="utf-8")
    for forbidden in (
        "import cv2",
        "VideoCapture(",
        "import socket",
        "import hidapi",
        "socket.",
    ):
        assert forbidden not in src


def test_occf_refuse_tools_closed_deny():
    a = occf.handle_refuse_actuator()
    assert a["ok"] is False
    assert a["deny_reason"] == "pad_not_on_this_plane"
    assert a["licenses_digits"] is False
    assert a["must_not_invent"]
    p = occf.handle_refuse_mid_drive_publish()
    assert p["ok"] is False
    assert p["deny_reason"] == "mid_drive_publish"
    assert p["licenses_digits"] is False


def test_occf_stdio_call_roundtrip(_offline_glass):
    resps = _rpc(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_observation", "arguments": {"jev_tail": 2}},
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "get_timeline", "arguments": {}},
            },
        ],
        env_extra={"QORESENCE_OCCF": "1"},
    )
    payload = _call_payload(resps[0])
    assert payload["plane"] == "qoresence-observation"
    assert payload["jev_tail"]["enabled"] is False  # ledger off → closed
    assert resps[1]["error"]["code"] == -32601  # get_timeline is not a tool


def test_occf_plugin_files_parse():
    root = Path("plugins/qoresence-observatory")
    plugin = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    mcp = json.loads((root / "mcp.json").read_text(encoding="utf-8"))
    assert plugin["licenses_digits"] is False
    assert plugin["plane"] == "qoresence-observation"
    srv = mcp["mcpServers"]["qoresence-observatory"]
    assert srv["env"]["QORESENCE_OCCF"] == "1"
    assert "qoresence.mcp.occf" in srv["args"]
    skill = (root / "skills" / "muse-observatory" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "get_observation" in skill
    assert "licenses_digits=false" in skill
