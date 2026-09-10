"""NarrativeEngine facade."""

from qoresence.foundry.narrative_engine import (
    NarrativeEngine,
    build_licensed_tick,
    generate_narrative,
    last_narrative,
    maybe_flush_live_narrative,
    note_licensed_tick,
)

__all__ = [
    "NarrativeEngine",
    "build_licensed_tick",
    "generate_narrative",
    "last_narrative",
    "maybe_flush_live_narrative",
    "note_licensed_tick",
]
