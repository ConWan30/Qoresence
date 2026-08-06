"""
Twitch EventSub WebSocket client for ClutchBot.

Listens for channel follow, subscription, and channel-point redemption events
and posts short thank-you / acknowledgement messages to chat. Runs in a
background thread using websockets' synchronous client.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from websockets.sync.client import connect

from .helix_client import TwitchHelixClient
from .twitch_client import TwitchIRCClient

log = logging.getLogger(__name__)

EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"


class TwitchEventSubClient:
    """Synchronous EventSub client over WebSocket."""

    def __init__(
        self,
        helix: TwitchHelixClient,
        irc: TwitchIRCClient | None,
        follow_alerts: bool = True,
        sub_alerts: bool = True,
        redemption_alerts: bool = True,
    ):
        self.helix = helix
        self.irc = irc
        self.follow_alerts = follow_alerts
        self.sub_alerts = sub_alerts
        self.redemption_alerts = redemption_alerts

        self._running = False
        self._thread: threading.Thread | None = None
        self._connection: Any | None = None
        self._subscribed_types: set[str] = set()

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        if self._running:
            return True

        if not self.helix.broadcaster_id:
            log.warning("EventSub requires broadcaster_id")
            return False

        current_user = self.helix.get_current_user()
        if not current_user:
            log.warning("EventSub could not resolve current user")
            return False

        self._bot_user_id = current_user["id"]

        self._running = True
        self._thread = threading.Thread(target=self._run, name="clutchbot-eventsub", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                log.debug(f"EventSub close error: {e}")
            self._connection = None
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNALS
    # ──────────────────────────────────────────────────────────────────────────

    def _run(self) -> None:
        while self._running:
            try:
                with connect(EVENTSUB_WS_URL, close_timeout=1) as ws:
                    self._connection = ws
                    self._handle_session(ws)
            except Exception as e:
                log.warning(f"EventSub connection error: {e}")
                if self._running:
                    time.sleep(5.0)

    def _handle_session(self, ws) -> None:
        log.info("EventSub WebSocket connected")
        while self._running:
            try:
                message = ws.recv(timeout=1.0)
            except TimeoutError:
                continue

            if message is None:
                break

            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                log.debug("EventSub non-JSON message")
                continue

            metadata = data.get("metadata", {})
            msg_type = metadata.get("message_type")
            if msg_type == "session_welcome":
                self._on_welcome(data)
            elif msg_type == "notification":
                self._on_notification(data)
            elif msg_type == "session_reconnect":
                log.info("EventSub requested reconnect")
                break
            elif msg_type == "revocation":
                sub_type = metadata.get("subscription_type", "unknown")
                log.warning(f"EventSub subscription revoked: {sub_type}")
            elif msg_type == "session_keepalive":
                pass

    def _on_welcome(self, data: dict[str, Any]) -> None:
        session_id = data["payload"]["session"]["id"]
        log.info(f"EventSub session welcome: {session_id[:8]}...")
        # New session means old subscriptions are gone; re-subscribe.
        self._subscribed_types.clear()
        self._subscribe(session_id)

    def _subscribe(self, session_id: str) -> None:
        broadcaster_id = self.helix.broadcaster_id
        if not broadcaster_id:
            return

        subs = []
        if self.follow_alerts:
            subs.append(("channel.follow", "2", {
                "broadcaster_user_id": broadcaster_id,
                "moderator_user_id": self._bot_user_id,
            }))
        if self.sub_alerts:
            subs.append(("channel.subscribe", "1", {
                "broadcaster_user_id": broadcaster_id,
            }))
        if self.redemption_alerts:
            subs.append(("channel.channel_points_custom_reward_redemption.add", "1", {
                "broadcaster_user_id": broadcaster_id,
            }))

        for sub_type, version, condition in subs:
            if sub_type in self._subscribed_types:
                continue
            result = self.helix.create_eventsub_subscription(sub_type, version, condition, session_id)
            if result:
                self._subscribed_types.add(sub_type)
                log.info(f"EventSub subscribed: {sub_type}")

    def _on_notification(self, data: dict[str, Any]) -> None:
        metadata = data.get("metadata", {})
        sub_type = metadata.get("subscription_type")
        event = data.get("payload", {}).get("event", {})

        if not self.irc:
            return

        if sub_type == "channel.follow":
            user = event.get("user_name", "someone")
            self.irc.send_message(f"Welcome to the channel, @{user}! 🎉")

        elif sub_type == "channel.subscribe":
            user = event.get("user_name", "someone")
            tier = event.get("tier", "1000")
            tier_name = {1000: "Tier 1", 2000: "Tier 2", 3000: "Tier 3"}.get(int(tier), "sub")
            self.irc.send_message(f"Thanks for the {tier_name} sub, @{user}! 💜")

        elif sub_type == "channel.channel_points_custom_reward_redemption.add":
            user = event.get("user_name", "someone")
            reward = event.get("reward", {}).get("title", "a reward")
            self.irc.send_message(f"@{user} redeemed {reward}! ✨")
