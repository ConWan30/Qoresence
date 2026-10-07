"""Rivalatch ship-receipt knock: frozen gate.run body, deep-link, Mobile Glass pill.

No network. No key on any page. Skip-closed when VIBEGATE_API_KEY is absent.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from qoresence.deck import rivalatch_knock as rk

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "qoresence" / "deck" / "rivalatch_knock.py"
SHA = "f980cda4887054ffd452db36a8a3ad531b1daac7"


def test_gate_body_is_frozen_shape():
    body = rk.build_gate_body(SHA, idempotency_key="k")
    assert body == {
        "app_ref": {"type": "git", "uri": "https://github.com/ConWan30/Qoresence", "rev": SHA},
        "checks": ["smoke"],
        "acceptance": {"criteria": [], "base_url_path": "/"},
        "idempotency_key": "k",
    }


@pytest.mark.parametrize("bad", ["", "f980cda", "main", "z" * 40, None])
def test_gate_body_rejects_non_full_sha(bad):
    with pytest.raises(ValueError):
        rk.build_gate_body(bad, idempotency_key="k")  # type: ignore[arg-type]


def test_deep_link_maps_onto_gate_run_keys():
    link = rk.build_deep_link(SHA)
    p = urlparse(link)
    assert p.scheme == "rivalatch" and p.netloc == "knock"
    q = {k: v[0] for k, v in parse_qs(p.query).items()}
    assert q == {
        "idempotency_key": f"qoresence-glass-{SHA}",
        "type": "git",
        "uri": "https://github.com/ConWan30/Qoresence",
        "rev": SHA,
        "checks": "smoke",
        "base_url_path": "/",
    }
    assert "key" not in link.lower().replace("idempotency_key", "")


def _fake_repo(tmp_path: Path, head: str, refs: dict[str, str] | None = None, packed: str = ""):
    gd = tmp_path / ".git"
    gd.mkdir()
    (gd / "HEAD").write_text(head + "\n", encoding="utf-8")
    for ref, sha in (refs or {}).items():
        p = gd / ref
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sha + "\n", encoding="utf-8")
    if packed:
        (gd / "packed-refs").write_text(packed, encoding="utf-8")
    return tmp_path


def test_local_tip_loose_ref(tmp_path: Path):
    root = _fake_repo(tmp_path, "ref: refs/heads/main", {"refs/heads/main": SHA})
    assert rk.local_git_tip(root) == {"sha": SHA, "ref": "refs/heads/main"}


def test_local_tip_packed_ref(tmp_path: Path):
    root = _fake_repo(
        tmp_path, "ref: refs/heads/main", packed=f"# pack-refs\n{SHA} refs/heads/main\n"
    )
    assert rk.local_git_tip(root)["sha"] == SHA


def test_local_tip_detached(tmp_path: Path):
    root = _fake_repo(tmp_path, SHA.upper())
    assert rk.local_git_tip(root)["sha"] == SHA


def test_no_git_is_hold_not_guess(tmp_path: Path):
    info = rk.knock_link_info(tmp_path)
    assert info["ok"] is False
    assert info["sha"] is None
    assert info["deep_link"] is None
    assert "HOLD" in info["note"]


def test_knock_link_info_never_carries_key(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("VIBEGATE_API_KEY", "sekrit-should-never-appear")
    root = _fake_repo(tmp_path, "ref: refs/heads/main", {"refs/heads/main": SHA})
    info = rk.knock_link_info(root)
    assert info["ok"] is True
    assert "sekrit" not in json.dumps(info)


def test_cli_skip_closed_without_key():
    env = {"PATH": "/usr/bin:/bin"}
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "lodge", "--sha", SHA],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert out.returncode == 0
    assert "skip-closed" in out.stdout


def test_lodge_reports_job_and_verdict(monkeypatch):
    calls = []

    def fake(method, url, api_key, *, body=None, timeout=120.0):
        calls.append((method, url, body))
        if method == "POST":
            return 202, {"job_id": "job-x", "state": "succeeded"}
        return 200, {"job_id": "job-x", "verdict": "pass", "fail_class": None, "checks": []}

    monkeypatch.setattr(rk, "_request", fake)
    res = rk.lodge(SHA, api_key="k", door="https://door.example")
    assert res["job_id"] == "job-x"
    assert res["verdict"] == "pass"
    assert res["door"] == "Lodged"
    assert calls[0][1] == "https://door.example/v1/gate/run"
    assert calls[0][2]["app_ref"]["rev"] == SHA
    assert calls[0][2]["idempotency_key"] == f"qoresence-ship-{SHA}"
    assert calls[1][1] == "https://door.example/v1/gate/results/job-x"


def test_mobile_glass_gets_knock_pill_only():
    from qoresence.deck.server import _html

    assert "rivalatch-knock.js" in _html("mobile.html")
    assert "rivalatch-knock.js" not in _html("deck.html")
    js = (ROOT / "qoresence" / "deck" / "rivalatch-knock.js").read_text(encoding="utf-8")
    assert "/api/rivalatch/knock-link" in js
    assert "Knock Rivalatch" in js
    assert "X-Api-Key" not in js and "VIBEGATE_API_KEY" not in js


def test_knock_link_route():
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from qoresence.deck.server import create_app

    client = TestClient(create_app())
    r = client.get("/api/rivalatch/knock-link")
    assert r.status_code == 200
    data = r.json()
    assert set(data) >= {"ok", "sha", "deep_link", "note"}
    if data["ok"]:
        assert data["deep_link"].startswith("rivalatch://knock?")
    js = client.get("/rivalatch-knock.js")
    assert js.status_code == 200
    m = client.get("/mobile.html")
    assert "rivalatch-knock.js" in m.text
