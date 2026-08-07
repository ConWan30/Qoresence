"""
Qoresence Fusion — Phase 6+

Exports:
- PresenceFusionEngine, PresenceReport, Anomaly, LobeContribution, FusionWeights
"""

# FusionWeights is defined in core.unified_config and re-exported here for convenience
from qoresence.core import FusionWeights

from .presence import (
    Anomaly,
    LobeContribution,
    PresenceFusionEngine,
    PresenceReport,
    create_fusion_engine,
)

__all__ = [
    "PresenceFusionEngine",
    "PresenceReport",
    "Anomaly",
    "LobeContribution",
    "create_fusion_engine",
    "FusionWeights",
]
