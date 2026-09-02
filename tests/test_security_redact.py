"""Security redaction and trusted-local client classification."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from qoresence.security.redact import (
    client_host_is_loopback,
    client_is_loopback,
    safe_http_body,
)


def test_safe_http_body_redacts_bearer_tokens_and_jpeg():
    leaked = (
        "model not found sk-secretTOKEN123 Bearer abc.def "
        "api_key=sk-other data:image/jpeg;base64,/9j/xxxx"
    )
    out = safe_http_body(leaked)
    assert "sk-secretTOKEN123" not in out
    assert "Bearer abc.def" not in out
    assert "/9j/xxxx" not in out
    assert "Bearer [redacted]" in out


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("testclient", True),
        ("::ffff:127.0.0.1", True),
        ("192.168.1.10", False),
        ("10.0.0.5", False),
        ("", False),
    ],
)
def test_client_host_is_loopback(host: str, expected: bool):
    assert client_host_is_loopback(host) is expected


def test_client_is_loopback_reads_fastapi_style_client():
    req = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    assert client_is_loopback(req) is True
    req_lan = SimpleNamespace(client=SimpleNamespace(host="192.168.4.22"))
    assert client_is_loopback(req_lan) is False


def test_llm_client_error_logs_redact_provider_body(caplog, monkeypatch):
    from qoresence.agents.llm_client import LLMConfig, QuicksilverLLMClient

    cfg = LLMConfig(enabled=True, api_key="unit-test-key", model="glm-5.3-flash")
    client = QuicksilverLLMClient(cfg)

    class _Resp:
        status_code = 400
        text = "Bearer leaked-token sk-secretTOKEN123 data:image/jpeg;base64,AAAA"

    class _Req:
        @staticmethod
        def post(*_a, **_k):
            return _Resp()

    caplog.set_level(logging.WARNING)
    monkeypatch.setattr("qoresence.agents.llm_client.HAS_REQUESTS", True)
    monkeypatch.setattr("qoresence.agents.llm_client.requests", _Req)
    assert client._post_chat([{"role": "user", "content": "hi"}]) is None

    assert "leaked-token" not in caplog.text
    assert "sk-secretTOKEN123" not in caplog.text
    assert "Bearer [redacted]" in caplog.text
