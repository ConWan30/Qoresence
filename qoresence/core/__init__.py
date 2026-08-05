"""
Qoresence Core — Phase 1 + 2

Exports:
- unified_config: RetinaUnifiedConfig, GameProfile, lobe configs
- session: SessionAuthority, SessionIdentity
- event_bus: RetinaEventBus, EventBusManager
- types: BaseEvent, SourceLobe, EventType, clock_ns, make_event
"""

from .unified_config import (
    RetinaUnifiedConfig,
    StreamerConfig,
    ControllerConfig,
    ScreenConfig,
    OutcomeConfig,
    VisualConfig,
    GameDetectionConfig,
    FusionWeights,
    GameProfileId,
    GameProfile,
    NCAA_FOOTBALL_27_PROFILE,
    CALL_OF_DUTY_PROFILE,
    get_game_profile,
    register_game_profile,
    GAME_PROFILE_REGISTRY,
)

from .session import SessionAuthority, SessionIdentity

from .event_bus import RetinaEventBus, EventBusManager

from .types import (
    BaseEvent,
    SourceLobe,
    EventType,
    clock_ns,
    make_event,
    StreamerPayload,
    ControllerPayload,
    ScreenPayload,
    OutcomePayload,
    VisualPayload,
    FusionPayload,
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
    "FusionWeights",
    "GameProfileId",
    "GameProfile",
    "NCAA_FOOTBALL_27_PROFILE",
    "CALL_OF_DUTY_PROFILE",
    "get_game_profile",
    "register_game_profile",
    "GAME_PROFILE_REGISTRY",
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