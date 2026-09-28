"""Fixture tests for Frame License Bureau export (license-pack-v0 / notary)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qoresence.license_bureau import export_rows, load_jsonl

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "seqgate_memory_receipts.jsonl"


@pytest.fixture(scope="module")
def rows():
    assert FIXTURE.is_file(), f"missing fixture: {FIXTURE}"
    return load_jsonl(FIXTURE)


def test_unstamped_refused_not_in_license_body(rows):
    pack, notary = export_rows(rows, session_id="t", tip_sha="9d78c37")
    unstamped_cases = {n["case"] for n in notary if n.get("reason") == "unstamped"}
    assert "unstamped_write" in unstamped_cases
    license_cases = {p.get("case") for p in pack if p.get("kind") == "license"}
    assert "unstamped_write" not in license_cases


def test_licensed_write_emits_license_row(rows):
    pack, _ = export_rows(rows, session_id="t", tip_sha="9d78c37")
    licensed = [
        p
        for p in pack
        if p.get("kind") == "license" and p.get("case") == "licensed_write"
    ]
    assert len(licensed) == 1
    assert licensed[0]["seqgate"] == "licensed"
    assert licensed[0]["frame_seq"] == 42


def test_stale_speech_hold_reason(rows):
    _, notary = export_rows(rows, session_id="t", tip_sha="9d78c37")
    stale = [n for n in notary if n.get("case") == "stale_speech"]
    assert stale
    assert any(n.get("reason") == "ticket_stale" for n in stale)
    assert all(n.get("seqgate") == "hold" for n in stale)


def test_no_invented_digits_in_export(rows):
    pack, notary = export_rows(rows, session_id="t", tip_sha="9d78c37")
    for line in pack + notary:
        if line.get("kind") in ("license", "notary", "manifest"):
            assert "home_score" not in line
            assert "away_score" not in line


def test_manifest_monetize_false(rows):
    pack, _ = export_rows(rows, session_id="t", tip_sha="9d78c37")
    assert pack[0]["kind"] == "manifest"
    assert pack[0]["monetize"] is False
    assert pack[0]["density_gate"] == "pending"
