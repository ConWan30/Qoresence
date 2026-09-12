"""Football observation adapter v0."""

from .adapter import FOOTBALL_ADAPTER, GAME_CATEGORY, POLICY_VERSION, FootballAdapter
from .phases import (
    ACTIVE_PHASES,
    BOUNDARY_GAME_STATES,
    BOUNDARY_PHASES,
    MOMENT_BOUNDARY_TIMEOUT_NS,
    VISUAL_PHASES,
)

__all__ = [
    "ACTIVE_PHASES",
    "BOUNDARY_GAME_STATES",
    "BOUNDARY_PHASES",
    "FOOTBALL_ADAPTER",
    "FootballAdapter",
    "GAME_CATEGORY",
    "MOMENT_BOUNDARY_TIMEOUT_NS",
    "POLICY_VERSION",
    "VISUAL_PHASES",
]
