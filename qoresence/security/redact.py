"""Redact secrets from logs and classify trusted local HTTP clients."""

from __future__ import annotations

import re
from typing import Any

_TRUSTED_LOCAL_CLIENTS = frozenset(
    {"127.0.0.1", "localhost", "::1", "[::1]", "testclient"}
)


def safe_http_body(text: str, *, limit: int = 400) -> str:
    """Log a provider body without keys, bearer tokens, or JPEG payloads."""
    raw = " ".join(str(text or "").split())
    raw = re.sub(r"(?i)bearer\s+[A-Za-z0-9._\-]+", "Bearer [redacted]", raw)
    raw = re.sub(r"sk-[A-Za-z0-9_\-]+", "sk-[redacted]", raw)
    raw = re.sub(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\"'\s]+", r"\1[redacted]", raw)
    raw = re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "data:image/[redacted]", raw)
    return raw[:limit]


def client_host_is_loopback(host: str | None) -> bool:
    h = str(host or "").strip().lower()
    if not h:
        return False
    if h in _TRUSTED_LOCAL_CLIENTS:
        return True
    if h.startswith("::ffff:127."):
        return True
    return False


def client_is_loopback(request: Any) -> bool:
    """True when the inbound HTTP client is loopback (or TestClient)."""
    try:
        client = getattr(request, "client", None)
        if client is not None:
            return client_host_is_loopback(getattr(client, "host", None))
    except Exception:
        return False
    return False
