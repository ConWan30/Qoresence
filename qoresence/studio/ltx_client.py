"""Thin LTX Video API client.

Implements the production async flow:
  1. POST /v1/upload  -> presigned upload URL + storage_uri
  2. PUT image bytes to the upload URL
  3. POST /v2/image-to-video with storage_uri as image_uri -> job id
  4. GET /v2/image-to-video/{id} until status is completed/failed
  5. GET result.video_url and save to disk

No new deps: uses `requests` if available, stdlib http otherwise.
API key is resolved from StudioConfig or `LTX_API_KEY` / `LTXV_API_KEY` env.
"""

from __future__ import annotations

import json
import logging
import pathlib
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.ltx.io"
_DEFAULT_ENDPOINT = "image-to-video"

# Official LTX-2.3 support matrix (1080p). Pro does not accept 5s.
_PRO_DURATIONS = (6, 8, 10)
_FAST_DURATIONS = (6, 8, 10, 12, 14, 16, 18, 20)


def normalize_duration(duration: int | None, model: str = "ltx-2-3-pro") -> int:
    """Snap a requested duration to a value the selected model accepts."""
    try:
        value = int(duration) if duration is not None else 6
    except (TypeError, ValueError):
        value = 6
    allowed = _FAST_DURATIONS if "fast" in (model or "") else _PRO_DURATIONS
    if value in allowed:
        return value
    return min(allowed, key=lambda item: abs(item - value))


try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    requests = None  # type: ignore
    HAS_REQUESTS = False


@dataclass
class UploadResult:
    """Result of a /v1/upload call."""

    storage_uri: str | None = None
    upload_url: str | None = None
    upload_method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def url_to_upload(self) -> str | None:
        return self.upload_url or self.storage_uri

    @property
    def url_to_use(self) -> str | None:
        return self.storage_uri or self.upload_url


@dataclass
class LtxJob:
    """Snapshot of an async LTX job."""

    job_id: str = ""
    status: str = "pending"  # pending | processing | completed | failed
    created_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def video_url(self) -> str | None:
        if self.result and isinstance(self.result, dict):
            return self.result.get("video_url") or self.result.get("url")
        return None

    @property
    def is_done(self) -> bool:
        return self.status in {"completed", "failed"}


def _strip_wrapping_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1].strip()
    return value


def _clean_api_key(value: str) -> str:
    """Extract an LTX token from a labeled or quoted secrets file."""
    for line in value.splitlines():
        line = _strip_wrapping_quotes(line)
        if not line or line.startswith("#"):
            continue
        tokens = line.replace(":", " ").split()
        for token in tokens:
            token = _strip_wrapping_quotes(token)
            if token.startswith(("ltxv_", "ltx_")):
                return token
        return tokens[-1] if tokens else line
    return _strip_wrapping_quotes(value)


def _resolve_api_key(api_key: str | None = None, api_key_file: str | None = None) -> str | None:
    if api_key and api_key.strip():
        return _clean_api_key(api_key)
    if api_key_file:
        try:
            p = pathlib.Path(api_key_file)
            if p.exists():
                return _clean_api_key(p.read_text(encoding="utf-8"))
            log.warning("LTX api_key_file not found: %s", api_key_file)
        except Exception as e:
            log.warning("LTX api_key_file read failed: %s", e)
    import os

    for k in ("LTX_API_KEY", "LTXV_API_KEY", "QORESENCE_STUDIO_API_KEY"):
        v = os.environ.get(k)
        if v and v.strip():
            return _clean_api_key(v)
    return None


def _json_with_error(resp: Any) -> dict[str, Any]:
    try:
        return resp.json() if callable(getattr(resp, "json", None)) else json.loads(resp.read())
    except Exception:
        return {}


class LtxClient:
    """OpenAI-compatible-ish client for the LTX video generation API."""

    def __init__(
        self,
        api_key: str | None = None,
        api_key_file: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        endpoint: str = _DEFAULT_ENDPOINT,
        timeout_s: float = 60.0,
        poll_interval_s: float = 5.0,
        max_poll_s: float = 600.0,
        upload_method: str | None = None,
        dry_run: bool = False,
    ):
        self._api_key = _resolve_api_key(api_key, api_key_file)
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint
        self.timeout_s = float(timeout_s)
        self.poll_interval_s = float(poll_interval_s)
        self.max_poll_s = float(max_poll_s)
        self.upload_method = (upload_method or "PUT").upper()
        self.dry_run = bool(dry_run)

    def is_available(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return urljoin(self.base_url + "/", path)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        expect_bytes: bool = False,
    ) -> tuple[int, dict[str, Any] | bytes]:
        """Low-level request with requests or stdlib fallback.

        `headers is None` attaches API auth for LTX JSON calls.
        Pass `headers={}` (or any dict) to send exactly those headers — required
        for GCS signed PUT/GET, which reject extra Authorization headers.
        """
        if not self._api_key and not self.dry_run:
            raise RuntimeError("LTX API key not configured")

        url = path if path.startswith(("http://", "https://")) else self._url(path)
        _timeout = timeout if timeout is not None else self.timeout_s
        if headers is not None:
            _headers = dict(headers)
        elif json_body is not None or method in {"GET", "POST"}:
            _headers = self._headers()
        else:
            _headers = {}
        if json_body is not None:
            _headers.setdefault("Content-Type", "application/json")

        if self.dry_run:
            log.info("[dry-run] %s %s", method, url)
            return 202, {"id": "dry-run", "status": "completed", "result": {"video_url": ""}}

        if HAS_REQUESTS:
            if json_body is not None:
                resp = requests.request(method, url, headers=_headers, json=json_body, timeout=_timeout)
            else:
                resp = requests.request(method, url, headers=_headers, data=data, timeout=_timeout)
            return resp.status_code, self._decode_response(
                resp.status_code,
                resp.headers.get("Content-Type", ""),
                resp.content,
                getattr(resp, "text", "") or "",
                expect_bytes=expect_bytes,
                json_loader=resp.json,
            )

        import http.client
        import urllib.parse

        parsed = urllib.parse.urlparse(url)
        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        conn = conn_cls(parsed.hostname or "", port, timeout=_timeout)
        body = json.dumps(json_body).encode() if json_body is not None else (data or b"")
        conn.request(method, (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else ""), body, _headers)
        resp = conn.getresponse()
        raw = resp.read()
        text = raw.decode("utf-8", errors="replace")
        return resp.status, self._decode_response(
            resp.status,
            resp.headers.get("Content-Type", ""),
            raw,
            text,
            expect_bytes=expect_bytes,
        )

    @staticmethod
    def _decode_response(
        status: int,
        content_type: str,
        raw: bytes,
        text: str,
        *,
        expect_bytes: bool = False,
        json_loader: Any | None = None,
    ) -> dict[str, Any] | bytes:
        ctype = (content_type or "").split(";")[0].strip().lower()
        if expect_bytes or ctype.startswith("video/") or ctype.startswith("application/octet-stream"):
            return raw
        looks_json = ctype.startswith(("application/json", "text/json")) or (
            text and text.lstrip().startswith(("{", "["))
        )
        if looks_json:
            try:
                if callable(json_loader):
                    return json_loader()
                return json.loads(text)
            except Exception:
                pass
        if 200 <= status < 300:
            return {} if not expect_bytes else raw
        return {"_raw": text}

    def upload_image(self, image_path: str | pathlib.Path) -> str:
        """Upload a local image and return the storage_uri for generation."""
        image_path = pathlib.Path(image_path)
        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        # 1. Get upload URL.
        status, body = self._request("POST", "/v1/upload", json_body={"content_type": "image/png"})
        if status not in (200, 201):
            raise RuntimeError(f"LTX upload init failed ({status}): {body}")
        if not isinstance(body, dict):
            raise RuntimeError("LTX upload init returned non-JSON")

        result = UploadResult(raw=body)
        result.storage_uri = body.get("storage_uri")
        result.upload_url = body.get("upload_url") or body.get("upload_uri") or body.get("signed_url")
        result.headers = body.get("required_headers") or body.get("upload_headers") or {}
        result.upload_method = (body.get("upload_method") or self.upload_method).upper()

        upload_url = result.url_to_upload
        if not upload_url:
            raise RuntimeError("LTX upload init did not return an upload URL")

        # 2. Upload file bytes.
        file_bytes = image_path.read_bytes()
        upload_headers = dict(result.headers)
        upload_headers.setdefault("Content-Type", "image/png")
        upload_headers.setdefault("Content-Length", str(len(file_bytes)))

        method = result.upload_method if result.upload_method in {"PUT", "POST"} else "PUT"
        up_status, up_body = self._request(
            method, upload_url, data=file_bytes, headers=upload_headers, timeout=120
        )
        if up_status not in (200, 201, 204):
            # Some storage endpoints return 200/204. 201 is also OK. Anything 2xx OK.
            if up_status < 200 or up_status >= 300:
                raise RuntimeError(f"LTX file upload failed ({up_status}): {up_body}")

        storage_uri = result.url_to_use
        if not storage_uri:
            raise RuntimeError("LTX upload did not return a usable storage_uri")
        return storage_uri

    def submit_image_to_video(
        self,
        image_uri: str,
        prompt: str,
        *,
        model: str = "ltx-2-3-pro",
        duration: int = 6,
        resolution: str = "1920x1080",
        aspect_ratio: str | None = None,
        fps: int | None = None,
        generate_audio: bool = False,
    ) -> LtxJob:
        """Submit an async image-to-video job."""
        payload: dict[str, Any] = {
            "image_uri": image_uri,
            "prompt": prompt,
            "model": model,
            "duration": normalize_duration(duration, model),
            "resolution": resolution,
            "generate_audio": generate_audio,
        }
        # Official V2 image-to-video has no aspect_ratio field; resolution encodes it.
        if fps:
            payload["fps"] = fps
        if aspect_ratio:
            log.debug("Ignoring aspect_ratio=%s (not in LTX V2 image-to-video)", aspect_ratio)

        path = f"/v2/{self.endpoint}"
        status, body = self._request("POST", path, json_body=payload)
        if status not in (200, 201, 202):
            raise RuntimeError(f"LTX submit failed ({status}): {body}")
        if not isinstance(body, dict):
            raise RuntimeError("LTX submit returned non-JSON")

        job_id = body.get("id") or body.get("job_id") or body.get("request_id")
        if not job_id:
            raise RuntimeError("LTX submit did not return a job id")

        return LtxJob(
            job_id=job_id,
            status=body.get("status", "pending"),
            created_at=body.get("created_at"),
            raw=body,
        )

    def get_job(self, job_id: str) -> LtxJob:
        """Poll the status of a single async job."""
        path = f"/v2/{self.endpoint}/{job_id}"
        status, body = self._request("GET", path)
        if status == 404:
            return LtxJob(job_id=job_id, status="failed", error="job not found or expired")
        if status != 200:
            return LtxJob(job_id=job_id, status="failed", error=f"HTTP {status}: {body}")
        if not isinstance(body, dict):
            return LtxJob(job_id=job_id, status="failed", error="non-JSON poll response")

        job_status = body.get("status", "pending")
        err = None
        if job_status == "failed":
            err = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else str(body)

        return LtxJob(
            job_id=job_id,
            status=job_status,
            created_at=body.get("created_at"),
            completed_at=body.get("completed_at"),
            result=body.get("result"),
            error=err,
            raw=body,
        )

    def poll_until_done(self, job_id: str) -> LtxJob:
        """Poll until the job reaches a terminal state or timeout."""
        start = time.time()
        while time.time() - start < self.max_poll_s:
            job = self.get_job(job_id)
            if job.is_done:
                return job
            time.sleep(self.poll_interval_s)
        return LtxJob(job_id=job_id, status="failed", error="polling timeout")

    def download_video(self, video_url: str, output_path: str | pathlib.Path) -> pathlib.Path:
        """Download a completed video to a local path."""
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Signed GCS URLs reject extra Authorization / Content-Type headers.
        status, body = self._request("GET", video_url, headers={}, timeout=120, expect_bytes=True)
        if status != 200:
            raise RuntimeError(f"LTX download failed ({status})")
        if not isinstance(body, bytes) or not body:
            raise RuntimeError("LTX download did not return video bytes")
        output_path.write_bytes(body)
        return output_path

    def render(
        self,
        image_path: str | pathlib.Path,
        prompt: str,
        output_path: str | pathlib.Path,
        **kwargs: Any,
    ) -> LtxJob:
        """Full pipeline: upload, submit, poll, download."""
        if self.dry_run:
            output_path = pathlib.Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"\x00" * 8)
            return LtxJob(job_id="dry-run", status="completed", result={"video_url": "dry-run"})
        storage_uri = self.upload_image(image_path)
        job = self.submit_image_to_video(storage_uri, prompt, **kwargs)
        job = self.poll_until_done(job.job_id)
        if job.status != "completed":
            return job
        video_url = job.video_url
        if not video_url:
            job.status = "failed"
            job.error = "completed but no video_url"
            return job
        self.download_video(video_url, output_path)
        return job
