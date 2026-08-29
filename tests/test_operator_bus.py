"""Operator RCP mailbox — enqueue-only, no RetinaEventBus, loopback HTTP."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qoresence.operator_bus.envelope import parse_envelope
from qoresence.operator_bus.mailbox import OperatorMailbox, get_operator_mailbox, reset_operator_mailbox


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    reset_operator_mailbox()
    monkeypatch.setenv("QORESENCE_OPERATOR_BUS_DIR", str(tmp_path / "ob"))
    yield
    reset_operator_mailbox()


def test_parse_requires_rcp_fields():
    with pytest.raises(ValueError):
        parse_envelope({"text": "hi"})
    env = parse_envelope(
        {
            "from": "qorector",
            "kind": "ticket",
            "path": "confirm",
            "text": "VLM null parse — HOLD merge",
            "evidence": {"age_s": 0.04},
        }
    )
    assert env.plane == "qoresence-observation"
    assert env.kind == "ticket"
    assert env.path == "confirm"
    assert env.id


def test_fast_path_strips_score_digits():
    env = parse_envelope(
        {
            "from": "qorewatch",
            "kind": "fact",
            "path": "fast",
            "text": "LIVE ok",
            "evidence": {"home_score": 21, "away_score": 17, "age_s": 0.02},
        }
    )
    assert "home_score" not in env.evidence
    assert "away_score" not in env.evidence
    assert env.evidence.get("age_s") == 0.02


def test_enqueue_does_not_emit_retina(tmp_path):
    src = Path(__file__).resolve().parents[1] / "qoresence" / "operator_bus" / "mailbox.py"
    text = src.read_text(encoding="utf-8")
    assert "emit_raw(" not in text
    assert "A2ABus(" not in text
    box = OperatorMailbox(root=tmp_path / "ob")
    env = box.enqueue_inbox(
        {
            "from": "qorector",
            "kind": "hold",
            "path": "hold",
            "text": "HOLD #111",
        }
    )
    assert env.id
    got = box.peek_inbox(1)
    assert got and got[0]["id"] == env.id


def test_outbox_roundtrip(tmp_path):
    box = get_operator_mailbox()
    box.enqueue_outbox(
        {
            "from": "grok-build",
            "to": "qorector",
            "kind": "fact",
            "path": "fast",
            "text": "LIVE age_s=0.04 crop=96x945",
            "evidence": {"age_s": 0.04, "crop_wh": [945, 96]},
        }
    )
    rows = box.peek_outbox(5)
    assert rows[-1]["from"] == "grok-build"
    assert rows[-1]["kind"] == "fact"


def test_prompt_mentions_localhost_and_hold():
    from qoresence.operator_bus.prompt import QOECTOR_BUS_PROMPT

    assert "127.0.0.1:8765/api/operator/bus" in QOECTOR_BUS_PROMPT
    assert "HOLD" in QOECTOR_BUS_PROMPT
    assert "vlm_last_crop" in QOECTOR_BUS_PROMPT
    assert "RetinaEventBus" in QOECTOR_BUS_PROMPT
