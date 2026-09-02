"""Security: Deck must stay on loopback by default (release gate)."""

from __future__ import annotations

import pytest


def test_deck_host_is_localhost():
    from qoresence.deck import server as deck_server

    host = getattr(deck_server, "DECK_HOST", None)
    assert host is not None, "DECK_HOST must be defined"
    assert host in ("127.0.0.1", "localhost", "::1"), (
        f"DECK_HOST must be loopback for release (got {host!r}). "
        "Do not bind 0.0.0.0 without an explicit operator override."
    )
    assert host != "0.0.0.0"


def test_deck_start_default_host_is_loopback():
    import inspect

    from qoresence.deck.server import DECK_HOST, start_deck

    sig = inspect.signature(start_deck)
    # default host parameter should match DECK_HOST
    host_param = sig.parameters.get("host")
    assert host_param is not None
    default = host_param.default
    if default is not inspect.Parameter.empty:
        assert default in ("127.0.0.1", "localhost", "::1", DECK_HOST)


def test_no_wildcard_bind_in_deck_module_source():
    """Static guard: deck server source must not advertise 0.0.0.0 as default."""
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "server.py"
    text = src.read_text(encoding="utf-8")
    # Allow comments mentioning 0.0.0.0 but not DECK_HOST = "0.0.0.0"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "DECK_HOST" in stripped and "0.0.0.0" in stripped:
            pytest.fail(f"DECK_HOST must not be 0.0.0.0: {stripped}")


@pytest.fixture
def deck_app():
    from qoresence.deck.server import create_app

    app = create_app()
    if app is None:
        pytest.skip("fastapi not installed")
    return app


def test_mutating_clip_route_rejects_non_loopback_client(deck_app, monkeypatch):
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")

    monkeypatch.setattr(
        "qoresence.security.redact.client_is_loopback",
        lambda _request: False,
    )
    client = TestClient(deck_app)
    resp = client.post("/api/clip", json={"seconds": 10})
    assert resp.status_code == 403
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "local_client_required"


def test_mutating_clip_route_allows_loopback_client(deck_app, monkeypatch):
    try:
        from fastapi.testclient import TestClient
    except Exception:
        pytest.skip("httpx/starlette TestClient not installed")

    class _Clip:
        path = "clips/hdmi_clip_test.mp4"
        duration_s = 10.0
        frames = 300
        width = 1280
        height = 720
        fps = 30.0
        size_bytes = 1234
        source = "test"

    monkeypatch.setattr(
        "qoresence.security.redact.client_is_loopback",
        lambda _request: True,
    )
    monkeypatch.setattr("qoresence.vision.clip_buffer.export_clip", lambda seconds=None: _Clip())

    client = TestClient(deck_app)
    resp = client.post("/api/clip", json={"seconds": 10})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
