"""
Qoresence Agents — optional autonomous consumers of observation events.

ClutchBot is the first agent: a controller-coupled, game-state-aware
Twitch chat companion that posts at clutch moments.
"""

from .action_executor import ActionExecutor
from .clutchbot import ClutchBotAgent
from .helix_client import TwitchHelixClient
from .moment_scorer import MomentScorer
from .session_memory import SessionMemory
from .situation_model import SituationModel
from .twitch_client import TwitchIRCClient

__all__ = [
    "ClutchBotAgent",
    "TwitchIRCClient",
    "TwitchHelixClient",
    "SituationModel",
    "MomentScorer",
    "ActionExecutor",
    "SessionMemory",
]
