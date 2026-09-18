"""Shared TypeSafe ask helper — timeout, warn-once, cadence, utf-8-sig key."""

from __future__ import annotations

import logging
import os
from unittest.mock import MagicMock

from qoresence.observability.typesafe_ask import (
    AskCadence,
    DEFAULT_ASK_INTERVAL_S,
    DEFAULT_TIMEOUT_S,
    ensure_typesafe_key,
    key_present,
    system_one,
)


def test_defaults_match_glass_contract():
    assert DEFAULT_TIMEOUT_S == 10.0
    assert DEFAULT_ASK_INTERVAL_S == 2.0


def test_ensure_typesafe_key_utf8_sig(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    secrets = tmp_path / ".secrets"
    secrets.mkdir()
    key_file = secrets / "typesafe.key"
    key_file.write_bytes(b"\xef\xbb\xbftest-key-value\n")
    monkeypatch.chdir(tmp_path)
    assert ensure_typesafe_key() is True
    assert os.environ["TYPESAFE_API_KEY"] == "test-key-value"
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def test_ensure_typesafe_key_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert ensure_typesafe_key() is False
    assert key_present() is False


def test_system_one_warns_once(monkeypatch, caplog):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    warned = [False]

    class Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def system_one(self, **kw):
            raise RuntimeError("simulated")

    monkeypatch.setattr(
        "qoresence.observability.typesafe_ask.open_typesafe_client",
        lambda **kw: Boom(),
    )
    lg = logging.getLogger("test_typesafe_ask_warn")
    with caplog.at_level(logging.WARNING, logger="test_typesafe_ask_warn"):
        assert (
            system_one(
                state={}, questions={}, warned_flag=warned, logger=lg, warn_label="unit"
            )
            is None
        )
        assert (
            system_one(
                state={}, questions={}, warned_flag=warned, logger=lg, warn_label="unit"
            )
            is None
        )
    warns = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(warns) == 1
    assert warned[0] is True


def test_system_one_passes_timeout_to_client(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "x")
    seen: dict = {}

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def system_one(self, **kw):
            seen["call"] = kw
            return MagicMock()

    def fake_open(**kw):
        seen["open"] = kw
        return Client()

    monkeypatch.setattr(
        "qoresence.observability.typesafe_ask.open_typesafe_client",
        fake_open,
    )
    assert system_one(state={"a": 1}, questions={"q": 1}, timeout_s=7.5) is not None
    assert seen["open"]["timeout_s"] == 7.5
    # SDK call may or may not accept timeout kw; either path is fine.
    assert seen["call"].get("timeout", 7.5) == 7.5 or "timeout" not in seen["call"]


def test_ask_cadence_reuses_and_rate_limits():
    cadence = AskCadence(ask_interval_s=10.0, reuse_s=30.0, warn_label="t")
    calls = {"n": 0}

    def ask():
        calls["n"] += 1
        return {"source": "typesafe", "v": calls["n"]}

    a1 = cadence.ask_or_reuse(ask)
    a2 = cadence.ask_or_reuse(ask)
    assert a1 == {"source": "typesafe", "v": 1}
    assert a2 == {"source": "typesafe", "v": 1}
    assert calls["n"] == 1
    assert cadence.stats()["typesafe_asks"] == 1
    assert cadence.stats()["typesafe_reuses"] == 1


def test_ask_cadence_counts_fail_when_none():
    cadence = AskCadence(ask_interval_s=0.0, reuse_s=0.0, warn_label="t")
    assert cadence.ask_or_reuse(lambda: None) is None
    assert cadence.stats()["typesafe_fails"] == 1


def test_older_packs_wire_shared_helper():
    """Conductor/noul/press/hygiene/coroner/stale/plausibility use shared ask."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "qoresence" / "observability"
    packs = [
        "jev_conductor.py",
        "noul_observatory.py",
        "press_labeler.py",
        "recap_hygiene.py",
        "sync_coroner.py",
        "ticket_stale.py",
        "score_plausibility.py",
    ]
    for name in packs:
        src = (root / name).read_text(encoding="utf-8")
        assert "from qoresence.observability.typesafe_ask import" in src, name
        assert "system_one(" in src, name
        assert "timeout_s=" in src, name
        assert "warned_flag=" in src, name
        # Must not open a bare client without timeout anymore.
        assert "TypeSafeClient()" not in src, name


def test_glass_packs_not_regressed_to_shared_helper():
    """TicketGlass / SyncGlass keep their #229-local ask path."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "qoresence" / "observability"
    for name in ("ticket_glass.py", "sync_glass.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "from qoresence.observability.typesafe_ask import" not in src, name
        assert "RetryPolicy(max_retries=0)" in src, name
        assert "_warned_typesafe" in src, name
