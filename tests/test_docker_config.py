"""Static Docker configuration safety checks."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_compose_defaults_to_loopback_and_no_restart_loop() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    service = compose["services"]["qoresence"]
    environment = service["environment"]

    assert any("QORESENCE_WS_HOST=${QORESENCE_WS_HOST:-127.0.0.1}" in item for item in environment)
    assert service["restart"] == "no"
    assert service["ports"] == ["127.0.0.1:8765:8765"]


def test_dockerfile_uses_only_repository_artifacts() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "vapi-pebble-prototype" not in dockerfile
    assert "COPY w3bstream_applet.wasm /app/w3bstream_applet.wasm" in dockerfile
    assert "HEALTHCHECK" not in dockerfile
