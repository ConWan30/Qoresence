"""Streamr Network publisher for Qoresence.

Publishes JSON events to a local Streamr node using the HTTP, MQTT, or WebSocket
plugin interface. The node signs and forwards the messages into the Streamr
Network. Protocol details:

- HTTP: POST /streams/{encoded_stream_id} with JSON body
- MQTT: publish(topic=stream_id, payload=json) to the node broker
- WebSocket: ws://host:port/streams/{encoded_stream_id}/publish

Reference:
    https://docs.streamr.network/guides/use-any-language-or-device/
    https://docs.streamr.network/usage/connect-apps-and-iot/streamr-node-interface/
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
from typing import Any

import paho.mqtt.client as mqtt

from qoresence.core import BaseEvent

log = logging.getLogger(__name__)


class StreamrPublisher:
    """Best-effort publisher of Qoresence events to a local Streamr node.

    - Never blocks the event bus: publishes in a background thread.
    - Degrades gracefully if the node is down or unreachable.
    - Throttles by event type and max events-per-second.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self._enabled = bool(config.enabled and config.stream_id)
        self._stream_id = config.stream_id
        self._protocol = (config.protocol or "http").lower()
        self._base_url = f"http://{config.host}:{config.port}"
        self._api_key = config.api_key
        self._timeout_s = float(config.timeout_s or 5.0)
        self._event_types = set(config.event_types or [])
        self._publish_all = "*" in self._event_types

        # Throttling
        self._max_eps = float(config.max_eps or 0.0)
        self._last_emit_t: float = 0.0
        self._emit_count_window: int = 0
        self._window_start: float = 0.0

        # Background queue
        self._queue: list[tuple[float, str, str]] = []
        self._queue_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()

        # MQTT state (lazily connected)
        self._mqtt: mqtt.Client | None = None
        self._mqtt_connected = False

        if self._enabled:
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="qoresence-streamr-publisher",
                daemon=True,
            )
            self._worker.start()
            log.info(
                "Streamr publisher enabled: stream=%s protocol=%s host=%s:%s",
                self._stream_id,
                self._protocol,
                config.host,
                config.port,
            )

    def publish(self, event: BaseEvent) -> None:
        """Queue an event for best-effort Streamr publishing."""
        if not self._enabled:
            return
        if not self._should_publish(event):
            return
        if not self._throttle_ok():
            return

        payload = json.dumps(event.to_dict(), default=_json_default)
        with self._queue_lock:
            self._queue.append((time.monotonic(), event.type, payload))

    def stop(self) -> None:
        """Stop the background publisher and close connections."""
        self._stop.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=2.0)
        if self._mqtt is not None:
            try:
                self._mqtt.disconnect()
            except Exception:
                pass
            self._mqtt = None

    def _should_publish(self, event: BaseEvent) -> bool:
        if self._publish_all:
            return True
        return str(getattr(event.type, "value", event.type)) in self._event_types

    def _throttle_ok(self) -> bool:
        if self._max_eps <= 0:
            return True
        now = time.monotonic()
        if now - self._window_start >= 1.0:
            self._window_start = now
            self._emit_count_window = 0
        if self._emit_count_window < self._max_eps:
            self._emit_count_window += 1
            return True
        return False

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            items: list[tuple[float, str, str]] = []
            with self._queue_lock:
                if self._queue:
                    items = self._queue[:10]  # batch up to 10
                    self._queue = self._queue[10:]
            if not items:
                time.sleep(0.05)
                continue
            try:
                if self._protocol == "http":
                    self._publish_http_batch(items)
                elif self._protocol == "mqtt":
                    self._publish_mqtt_batch(items)
                elif self._protocol == "websocket":
                    self._publish_ws_batch(items)
                else:
                    log.warning("Unsupported Streamr protocol: %s", self._protocol)
                    return
            except Exception as e:
                log.debug("Streamr publish batch failed: %s", e)

    def _publish_http_batch(self, items: list[tuple[float, str, str]]) -> None:
        encoded = urllib.parse.quote(self._stream_id, safe="")
        url = f"{self._base_url}/streams/{encoded}"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"bearer {self._api_key}"
        for _, _ev_type, payload in items:
            req = urllib.request.Request(
                url,
                data=payload.encode("utf-8"),
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout_s) as resp:
                if resp.status >= 300:
                    log.debug("Streamr HTTP error: %s", resp.status)

    def _publish_mqtt_batch(self, items: list[tuple[float, str, str]]) -> None:
        if self._mqtt is None:
            self._mqtt = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=f"qoresence-{time.time_ns() % 1_000_000}",
            )
            if self._api_key:
                self._mqtt.username_pw_set("x", self._api_key)
            try:
                self._mqtt.connect(
                    self.config.host,
                    int(self.config.port or 1883),
                    keepalive=30,
                )
                self._mqtt.loop_start()
                self._mqtt_connected = True
            except Exception as e:
                log.warning("Streamr MQTT connect failed: %s", e)
                return
        for _, _ev_type, payload in items:
            info = self._mqtt.publish(self._stream_id, payload, qos=1)
            info.wait_for_publish(timeout=self._timeout_s)

    def _publish_ws_batch(self, items: list[tuple[float, str, str]]) -> None:
        # WebSocket support can be added later without breaking the API.
        # For now, fall back to HTTP if the user selected websocket.
        log.debug("WebSocket publisher not yet implemented; falling back to HTTP")
        self._publish_http_batch(items)


def _json_default(obj: Any) -> Any:
    """Serialize non-JSON-native objects as strings."""
    try:
        return obj.to_dict()
    except Exception:
        return str(obj)


def make_streamr_publisher_from_config(config: Any) -> StreamrPublisher | None:
    """Factory used by cli.py / event bus wiring."""
    if not getattr(config, "enabled", False):
        return None
    if not getattr(config, "stream_id", "").strip():
        return None
    return StreamrPublisher(config)
