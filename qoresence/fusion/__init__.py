"""
Qoresence Fusion — Phase 6+

Exports:
- PresenceFusionEngine, PresenceReport, Anomaly, LobeContribution, FusionWeights
"""

from .presence import (
    PresenceFusionEngine,
    PresenceReport,
    Anomaly,
    LobeContribution,
    create_fusion_engine,
)

# FusionWeights is defined in core.unified_config and re-exported here for convenience
from qoresence.core import FusionWeights

__all__ = [
    "PresenceFusionEngine",
    "PresenceReport",
    "Anomaly",
    "LobeContribution",
    "create_fusion_engine",
    "FusionWeights",
]