"""TimingCoach facade. Implementation lives in ``qoresence.foundry.timing_coach``.

Not imported from ``qoresence.agents`` package init (avoids pulling capture deps).
"""

from qoresence.foundry.timing_coach import (
    TimingCoach,
    generate_timing_report,
    last_timing_report,
    refresh_after_clip_export,
)

__all__ = [
    "TimingCoach",
    "generate_timing_report",
    "last_timing_report",
    "refresh_after_clip_export",
]
