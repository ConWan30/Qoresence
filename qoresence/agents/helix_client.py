"""
Twitch Helix API client for ClutchBot.

Creates clips and channel-point predictions. This is intentionally minimal
so it can be swapped for a richer library later without touching the agent.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

HELIX_URL = "https://api.twitch.tv/helix"


@dataclass
class ClipResult:
    id: str
    edit_url: str
    created_at: str


@dataclass
class PredictionResult:
    id: str
    title: str
    outcomes: list[dict[str, Any]]
    status: str


class TwitchHelixClient:
    """Synchronous Helix client."""

    def __init__(
        self,
        client_id: str,
        access_token: str,
        broadcaster_id: str | None = None,
        broadcaster_username: str | None = None,
    ):
        self.client_id = client_id.strip()
        self.access_token = self._normalize_token(access_token)
        self.broadcaster_id = broadcaster_id
        self.broadcaster_username = (broadcaster_username or "").lower().strip()

        self._session = requests.Session()
        self._last_clip: ClipResult | None = None
        self._last_clip_time = 0.0
        self._active_prediction: PredictionResult | None = None
        self._prediction_start_ns: int | None = None

    @staticmethod
    def _normalize_token(token: str) -> str:
        token = token.strip()
        if token.lower().startswith("oauth:"):
            return token[6:]
        return token

    # ──────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Validate credentials and resolve broadcaster_id if needed."""
        if not self.broadcaster_id:
            if not self.broadcaster_username:
                log.error("Helix client needs broadcaster_id or broadcaster_username")
                return False
            self.broadcaster_id = self._resolve_user_id(self.broadcaster_username)
            if not self.broadcaster_id:
                log.error(f"Could not resolve broadcaster_id for {self.broadcaster_username}")
                return False

        user = self._get_user(self.broadcaster_id)
        if not user:
            log.error("Helix token does not have permission to read broadcaster user")
            return False

        log.info(f"Helix client ready for broadcaster {user.get('display_name')} ({self.broadcaster_id})")
        return True

    def stop(self) -> None:
        self._session.close()

    def create_clip(self, has_delay: bool = False) -> ClipResult | None:
        """Create a clip for the configured broadcaster."""
        if not self.broadcaster_id:
            log.warning("Cannot create clip: no broadcaster_id")
            return None

        now = time.time()
        if now - self._last_clip_time < 60.0:
            log.debug("Clip cooldown active")
            return None

        url = f"{HELIX_URL}/clips"
        params = {"broadcaster_id": self.broadcaster_id, "has_delay": str(has_delay).lower()}
        data = self._post(url, params)

        if not data or not data.get("data"):
            log.error("Helix create_clip returned no data")
            return None

        clip = data["data"][0]
        self._last_clip_time = time.time()
        self._last_clip = ClipResult(
            id=clip["id"],
            edit_url=clip["edit_url"],
            created_at=clip["created_at"],
        )
        return self._last_clip

    def create_prediction(
        self,
        title: str,
        outcomes: list[str],
        window_s: int = 120,
    ) -> PredictionResult | None:
        """Create a channel-point prediction."""
        if not self.broadcaster_id:
            log.warning("Cannot create prediction: no broadcaster_id")
            return None

        if self._active_prediction:
            log.debug("A prediction is already active")
            return None

        if len(outcomes) < 2:
            log.error("Prediction needs at least 2 outcomes")
            return None

        url = f"{HELIX_URL}/predictions"
        payload = {
            "broadcaster_id": self.broadcaster_id,
            "title": title,
            "outcomes": [{"title": o} for o in outcomes[:2]],
            "prediction_window": min(window_s, 1800),
        }
        data = self._post(url, json=payload)

        if not data or not data.get("data"):
            log.error("Helix create_prediction returned no data")
            return None

        pred = data["data"][0]
        self._active_prediction = PredictionResult(
            id=pred["id"],
            title=pred["title"],
            outcomes=pred["outcomes"],
            status=pred["status"],
        )
        self._prediction_start_ns = time.time_ns()
        return self._active_prediction

    def resolve_prediction(self, winning_outcome_index: int) -> bool:
        """Resolve the active prediction."""
        if not self._active_prediction:
            log.warning("No active prediction to resolve")
            return False

        pred = self._active_prediction
        if winning_outcome_index < 0 or winning_outcome_index >= len(pred.outcomes):
            log.error("Winning outcome index out of range")
            return False

        winning_id = pred.outcomes[winning_outcome_index]["id"]
        url = f"{HELIX_URL}/predictions"
        payload = {
            "broadcaster_id": self.broadcaster_id,
            "id": pred.id,
            "status": "RESOLVED",
            "winning_outcome_id": winning_id,
        }
        data = self._patch(url, json=payload)
        success = bool(data and data.get("data"))
        if success:
            self._active_prediction = None
            self._prediction_start_ns = None
        return success

    def cancel_prediction(self) -> bool:
        """Cancel the active prediction."""
        if not self._active_prediction:
            return True

        url = f"{HELIX_URL}/predictions"
        payload = {
            "broadcaster_id": self.broadcaster_id,
            "id": self._active_prediction.id,
            "status": "CANCELED",
        }
        data = self._patch(url, json=payload)
        success = bool(data and data.get("data"))
        if success:
            self._active_prediction = None
            self._prediction_start_ns = None
        return success

    @property
    def active_prediction(self) -> PredictionResult | None:
        return self._active_prediction

    @property
    def last_clip_url(self) -> str | None:
        return self._last_clip.edit_url if self._last_clip else None

    def get_current_user(self) -> dict[str, Any] | None:
        """Return the user associated with the current access token."""
        data = self._get(f"{HELIX_URL}/users")
        if data and data.get("data"):
            return data["data"][0]
        return None

    def create_eventsub_subscription(
        self,
        subscription_type: str,
        version: str,
        condition: dict[str, str],
        session_id: str,
    ) -> str | None:
        """Create an EventSub subscription over a WebSocket session."""
        url = f"{HELIX_URL}/eventsub/subscriptions"
        payload = {
            "type": subscription_type,
            "version": version,
            "condition": condition,
            "transport": {"method": "websocket", "session_id": session_id},
        }
        data = self._post(url, json=payload)
        if not data or not data.get("data"):
            log.warning(f"Failed to create EventSub {subscription_type}: {data}")
            return None
        return data["data"][0].get("id")

    # ──────────────────────────────────────────────────────────────────────────
    # INTERNALS
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_user_id(self, login: str) -> str | None:
        data = self._get(f"{HELIX_URL}/users", {"login": login})
        if data and data.get("data"):
            return data["data"][0]["id"]
        return None

    def _get_user(self, user_id: str) -> dict[str, Any] | None:
        data = self._get(f"{HELIX_URL}/users", {"id": user_id})
        if data and data.get("data"):
            return data["data"][0]
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Client-Id": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            resp = self._session.get(url, headers=self._headers(), params=params, timeout=15)
            return self._handle(resp)
        except requests.RequestException as e:
            log.error(f"Helix GET failed: {e}")
            return None

    def _post(self, url: str, params: dict[str, Any] | None = None, json: Any | None = None) -> dict[str, Any] | None:
        try:
            resp = self._session.post(url, headers=self._headers(), params=params, json=json, timeout=15)
            return self._handle(resp)
        except requests.RequestException as e:
            log.error(f"Helix POST failed: {e}")
            return None

    def _patch(self, url: str, json: Any) -> dict[str, Any] | None:
        try:
            resp = self._session.patch(url, headers=self._headers(), json=json, timeout=15)
            return self._handle(resp)
        except requests.RequestException as e:
            log.error(f"Helix PATCH failed: {e}")
            return None

    def _handle(self, resp: requests.Response) -> dict[str, Any] | None:
        if resp.status_code == 204:
            return {}

        if not resp.ok:
            log.error(f"Helix error {resp.status_code}: {resp.text[:200]}")
            return None

        try:
            return resp.json()
        except ValueError:
            log.error("Helix non-JSON response")
            return None
