"""Same-Seq join_ok JSONL append rate — gate stays hot, log stays quiet."""

from __future__ import annotations

import pytest

from qoresence.graphs import reset_all
from qoresence.graphs.flags import ENV_NAME
from qoresence.graphs.look_license import load_licenses
from qoresence.graphs.same_seq_join import classify_join, confirm_look_allowed, last_license


@pytest.fixture(autouse=True)
def _graphs_reset(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_NAME, raising=False)
    monkeypatch.setenv(ENV_NAME, "1")
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(tmp_path / "look.jsonl"))
    reset_all()
    yield
    reset_all()


def test_join_ok_60fps_sampled_jsonl_not_per_frame(tmp_path):
    path = tmp_path / "look.jsonl"
    for i in range(1, 61):
        classify_join(
            live_seq=i,
            widget_seq=i,
            hid_seq=i,
            clock_ns=i * 1_000_000,
        )
    rows = load_licenses(path)
    assert len(rows) <= 3
    assert len(rows) >= 2
    assert confirm_look_allowed(last_license()) is True
    assert last_license() is not None
    assert last_license().kind == "join_ok"


def test_seq_skew_still_appends_each_transition(tmp_path):
    path = tmp_path / "look.jsonl"
    classify_join(live_seq=100, widget_seq=100, clock_ns=1)
    classify_join(live_seq=100, widget_seq=1, clock_ns=2)
    classify_join(live_seq=101, widget_seq=1, clock_ns=3)
    rows = load_licenses(path)
    assert len(rows) == 3
    assert rows[0].kind == "join_ok"
    assert rows[1].kind == "seq_skew"
    assert rows[2].kind == "seq_skew"


def test_gate_hot_when_jsonl_quiet(tmp_path):
    path = tmp_path / "look.jsonl"
    lic = None
    for i in range(1, 61):
        lic = classify_join(live_seq=i, widget_seq=i, clock_ns=i * 1_000_000)
    assert lic is not None
    assert lic.kind == "join_ok"
    assert confirm_look_allowed(lic) is True
    assert len(load_licenses(path)) <= 3
