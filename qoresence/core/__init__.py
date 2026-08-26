"""
Qoresence Core — Phase 1 + 2

Exports:
- unified_config: RetinaUnifiedConfig, GameProfile, lobe configs
- session: SessionAuthority, SessionIdentity
- event_bus: RetinaEventBus, EventBusManager
- types: BaseEvent, SourceLobe, EventType, clock_ns, make_event
"""

from .event_bus import EventBusManager, RetinaEventBus
from .session import SessionAuthority, SessionIdentity
from .types import (
    BaseEvent,
    ControllerPayload,
    EventType,
    FusionPayload,
    OutcomePayload,
    ScreenPayload,
    SourceLobe,
    StreamerPayload,
    VisualPayload,
    clock_ns,
    make_event,
)
from .unified_config import (
    CALL_OF_DUTY_PROFILE,
    GAME_PROFILE_ALIASES,
    GAME_PROFILE_REGISTRY,
    MADDEN_27_PROFILE,
    NCAA_FOOTBALL_27_PROFILE,
    AgentGlassConfig,
    ClutchBotConfig,
    ControllerConfig,
    FusionWeights,
    GameDetectionConfig,
    GameProfile,
    GameProfileId,
    HapticProbeConfig,
    OtelConfig,
    OutcomeConfig,
    RetinaUnifiedConfig,
    ScreenConfig,
    StemConfig,
    StreamerConfig,
    TwitchConfig,
    VisualConfig,
    get_game_profile,
    normalize_game_profile,
    register_game_profile,
)

__all__ = [
    # unified_config
    "RetinaUnifiedConfig",
    "StreamerConfig",
    "ControllerConfig",
    "ScreenConfig",
    "OutcomeConfig",
    "VisualConfig",
    "GameDetectionConfig",
    "AgentGlassConfig",
    "ClutchBotConfig",
    "OtelConfig",
    "HapticProbeConfig",
    "StemConfig",
    "TwitchConfig",
    "FusionWeights",
    "GameProfileId",
    "GameProfile",
    "NCAA_FOOTBALL_27_PROFILE",
    "MADDEN_27_PROFILE",
    "CALL_OF_DUTY_PROFILE",
    "get_game_profile",
    "normalize_game_profile",
    "register_game_profile",
    "GAME_PROFILE_REGISTRY",
    "GAME_PROFILE_ALIASES",
    # session
    "SessionAuthority",
    "SessionIdentity",
    # event_bus
    "RetinaEventBus",
    "EventBusManager",
    # types
    "BaseEvent",
    "SourceLobe",
    "EventType",
    "clock_ns",
    "make_event",
    "StreamerPayload",
    "ControllerPayload",
    "ScreenPayload",
    "OutcomePayload",
    "VisualPayload",
    "FusionPayload",
]
