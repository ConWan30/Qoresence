"""
Qoresence Agents — optional autonomous consumers of observation events.

ClutchBot is the first agent: a controller-coupled, game-state-aware
Twitch chat companion that posts at clutch moments.
"""

from .action_executor import ActionExecutor
from .clutchbot import ClutchBotAgent
from .eventsub_client import TwitchEventSubClient
from .helix_client import TwitchHelixClient
from .drive_graph import DriveGraph, active_drive_graph
from .fast_moment import FastMomentEngine
from .moment_scorer import MomentScorer
from .prediction_lifecycle import PredictionLifecycleManager, get_prediction_lifecycle
from .session_memory import SessionMemory
from .session_timeline import SessionTimeline, get_session_timeline
from .situation_model import SituationModel
from .twitch_client import TwitchIRCClient

__all__ = [
    "ClutchBotAgent",
    "TwitchIRCClient",
    "TwitchHelixClient",
    "TwitchEventSubClient",
    "SituationModel",
    "MomentScorer",
    "FastMomentEngine",
    "DriveGraph",
    "active_drive_graph",
    "SessionTimeline",
    "get_session_timeline",
    "PredictionLifecycleManager",
    "get_prediction_lifecycle",
    "ActionExecutor",
    "SessionMemory",
]
