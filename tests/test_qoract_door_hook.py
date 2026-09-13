"""WP-D: QORESENCE_QORACT_DOOR default OFF. Fail-open. No QorAct import."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.foundry import qoract_door
from qoresence.foundry.qoract_door import (
    maybe_spawn_qoract_door,
    persist_and_maybe_door,
    write_recap_file,
)

RECAP = {
    "schema": "session-recap-1",
    "ok": True,
    "status": "live",
    "session": "qoresence_06b8c404882b",
    "event_count": 1,
    "events": [],
}


def test_env_unset_does_not_spawn_and_recap_unchanged(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_QORACT_DOOR", raising=False)
    recap_path = tmp_path / "session-recap.json"
    write_recap_file(recap_path, RECAP)
    before = recap_path.read_text(encoding="utf-8")
    calls: list = []

    def boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("must not spawn")

    out = persist_and_maybe_door(
        recap=RECAP,
        recap_path=recap_path,
        qoract_root=tmp_path / "QorAct",
        spawn=boom,
    )
    assert out["spawned"] is False
    assert calls == []
    assert recap_path.read_text(encoding="utf-8") == before
    assert json.loads(before)["schema"] == "session-recap-1"


def test_env_on_missing_script_still_writes_recap(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_QORACT_DOOR", "1")
    recap_path = tmp_path / "audits" / "session-recap.json"
    out = persist_and_maybe_door(
        recap=RECAP,
        recap_path=recap_path,
        qoract_root=tmp_path / "no-such-qoract",
    )
    assert recap_path.is_file()
    body = json.loads(recap_path.read_text(encoding="utf-8"))
    assert body["schema"] == "session-recap-1"
    assert body["session"] == "qoresence_06b8c404882b"
    assert out["wrote"] is True
    assert out["spawned"] is False


def test_env_on_fake_recap_path_attempts_subprocess_and_returns(tmp_path, monkeypatch):
    monkeypatch.setenv("QORESENCE_QORACT_DOOR", "1")
    scripts = tmp_path / "QorAct" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "issue_from_recap.py").write_text("# fake door\n", encoding="utf-8")
    calls: list = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "timeout": kwargs.get("timeout")})
        raise RuntimeError("door died")

    recap_path = tmp_path / "missing" / "nope.json"
    out = maybe_spawn_qoract_door(
        recap_path,
        recap=RECAP,
        qoract_root=tmp_path / "QorAct",
        spawn=fake_run,
    )
    assert out["spawned"] is True
    assert calls
    assert "issue_from_recap.py" in str(calls[0]["cmd"])
    assert "--recap" in calls[0]["cmd"]
    assert calls[0]["timeout"] is not None


def test_streamer_runtime_does_not_import_door():
    src = Path(__file__).resolve().parents[1] / "qoresence" / "lobes" / "streamer.py"
    blob = src.read_text(encoding="utf-8")
    assert "qoract_door" not in blob
    assert "issue_from_recap" not in blob
    assert "qoract" not in blob.lower()


def test_door_module_does_not_import_qoract_package():
    src = Path(qoract_door.__file__).read_text(encoding="utf-8")
    assert "import qoract" not in src
    assert "from qoract" not in src
