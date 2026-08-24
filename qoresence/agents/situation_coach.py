"""SituationCoach facade."""

from qoresence.foundry.situation_coach import (
    SituationCoach,
    generate_situation_report,
    last_situation_report,
)

__all__ = ["SituationCoach", "generate_situation_report", "last_situation_report"]
