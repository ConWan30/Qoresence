"""
Qoresence Agents — optional autonomous consumers of observation events.

ClutchBot is the first agent: a controller-coupled, game-state-aware
companion that posts clutch moments to Deck feed and local HDMI clips.
Twitch IRC/Helix backends are leftover and default-OFF.
"""

from .action_executor import ActionExecutor
from .clutchbot import ClutchBotAgent
from .drive_graph import DriveGraph, active_drive_graph
from .eventsub_client import TwitchEventSubClient
from .fast_moment import FastMomentEngine
from .helix_client import TwitchHelixClient
from .match_agent import MatchAgent, start_match_agent, stop_match_agent
from .moment_scorer import MomentScorer
from .prediction_lifecycle import PredictionLifecycleManager, get_prediction_lifecycle
from .session_memory import SessionMemory
from .session_timeline import SessionTimeline, get_session_timeline
from .situation_model import SituationModel
from .twitch_client import TwitchIRCClient

__all__ = [
    "ClutchBotAgent",
    "MatchAgent",
    "start_match_agent",
    "stop_match_agent",
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
