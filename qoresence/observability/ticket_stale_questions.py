"""TypeSafe questions for the ticket_stale / soft_board freshness pack.

ONE constants module: every question, option set, and gate threshold for the
pack lives here. Question IDs are for code; meaning lives in instructions.

The pack observes the live-board stuck-lock class: a confirm ticket that still
licenses old digits while the VLM crop / live board has moved on. It never
mints scores, never emits bus events, never takes lobe locks —
``licenses_digits`` is False forever.
"""

from __future__ import annotations

from typing import Any

# Confidence gates (AGENTS.md observation-plane policy; same bands as the
# SyncCoroner): >= ACT acts, SOFT..ACT is a soft/watch verdict, < SOFT observe.
CONF_ACT = 0.7
CONF_SOFT = 0.4

# Deterministic staleness inputs (mirror digit_integrity, not a second gate).
STALE_AFTER_NS = 8_000_000_000

# Closed stuck-lock classes — Choice options. Include no_match-style "fresh".
STALE_CLASSES = (
    "fresh",
    "crop_moved_on",
    "match_changed",
    "menu_or_plate",
    "clock_drift",
    "unknown",
)

# Actions the pack may report. Advisory only — code owns the real blank path.
ACTIONS = ("flag_stale", "watch", "observe")


def ticket_stale_questions() -> dict[str, Any]:
    """One request: stuck-lock class + hold noul + freshness score."""
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}
    return {
        "stale_class": Choice(
            instructions={
                "question": (
                    "`ticket` is the licensed confirm ticket (scores + crop_hash "
                    "+ clock it minted on) and `live` is what the HDMI crop / VLM "
                    "shows now. Which stuck-lock class best explains the pair?"
                ),
                "focus": "Classify the drift only — code owns tickets, clocks, and digit licensing.",
                "never": "Never prescribe a fix; never mint or restate digits.",
            },
            criteria={
                "fresh": {"what": "Ticket and live crop describe the same live board."},
                "crop_moved_on": {
                    "what": "Crop/parse moved on (new frame, new HUD state) but the ticket still licenses the old digits.",
                },
                "match_changed": {
                    "what": "Live evidence describes a different matchup or score identity than the ticket.",
                },
                "menu_or_plate": {
                    "what": "Live crop is a menu, pause plate, or empty board while the ticket still licenses digits.",
                },
                "clock_drift": {
                    "what": "Same board, but the ticket clock is aging toward the stale bound without refresh.",
                },
                "unknown": {"what": "Not enough live evidence to classify."},
            },
        ),
        "hold_now": Noul(
            instructions={
                "question": (
                    "Should the licensed board be treated as stale right now — "
                    "i.e. painting the ticket's digits would repeat an old match "
                    "the crop has left behind?"
                ),
                "true": "Ticket licenses digits the live board no longer supports.",
                "false": "Ticket still matches the live board.",
                "never": "Observation only — SEQGATE/digit_integrity own the actual blank.",
            },
        ),
        "freshness": Score(
            instructions={
                "question": "How fresh is the licensed confirm ticket against the live crop?",
                "focus": "Rate observed evidence, not the capture pipeline.",
                "never": "Not a quality rating of the VLM.",
            },
            criteria=[
                "Stale — ticket licenses digits the crop has clearly left behind.",
                "Aging — same board but ticket clock or crop is drifting.",
                "Fresh — ticket and live crop agree on a live board.",
            ],
        ),
    }
