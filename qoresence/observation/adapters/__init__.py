"""Game observation adapters — sport/title rules outside the generic reducer."""

from __future__ import annotations

import os

from .football import FOOTBALL_ADAPTER, FootballAdapter
from .protocol import GameObservationAdapter

__all__ = [
    "FOOTBALL_ADAPTER",
    "FootballAdapter",
    "GameObservationAdapter",
    "football_adapter_enabled",
    "resolve_adapter",
]


def football_adapter_enabled() -> bool:
    """Explicit opt-in or auto-select when observations runtime is on."""
    if os.getenv("QORESENCE_FOOTBALL_ADAPTER", "").strip().lower() in {
        "1",
        "true",
        "on",
    }:
        return True
    from qoresence.observation.lifecycle import observations_enabled

    return observations_enabled()


def resolve_adapter(game_category: str | None) -> GameObservationAdapter | None:
    """Return an adapter for the category, or abstain (never invent football)."""
    if game_category != FOOTBALL_ADAPTER.game_category:
        return None
    if not football_adapter_enabled():
        return None
    return FOOTBALL_ADAPTER
