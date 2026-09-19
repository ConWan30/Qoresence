"""TypeSafe questions for the join-picker pack.

ONE constants module. Question IDs are for code; meaning lives in instructions.

Jev selects which already-stamped hid_seq_line slot belongs on the current
HDMI frame. It never invents a lag, never interpolates, never licenses digits.
"""

from __future__ import annotations

from typing import Any

CONF_ACT = 0.7
CONF_SOFT = 0.4

JOIN_IDS = ("behind_2", "behind_1", "now", "ahead_1", "none")
ACT_KINDS = ("snap", "sprint", "cut", "menu_stick", "idle", "unknown")
ACTIONS = ("stamp", "observe", "dark")

PLAY_PHASES = frozenset(
    {
        "snap",
        "running",
        "passing",
        "ball_in_air",
        "coverage",
        "defense_pursuit",
        "defense_engaged",
        "blocking",
        "player_locked_receiver",
    }
)
MENU_HUD = frozenset({"menu", "select_plate", "loading", "no_board"})


def join_picker_questions() -> dict[str, Any]:
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}
    return {
        "join_id": Choice(
            instructions={
                "question": (
                    "Which already-stamped HID slot in `candidates` belongs on "
                    "the current HDMI frame described by `picture`?"
                ),
                "focus": "Select a stored slot. Never invent a lag or pose.",
                "never": "none when no slot is an honest pad↔picture join.",
            },
            criteria={
                "behind_2": {"what": "`candidates.behind_2` is present and is the honest join."},
                "behind_1": {"what": "`candidates.behind_1` is present and is the honest join."},
                "now": {"what": "`candidates.now` (current hub seq) is the honest join."},
                "ahead_1": {"what": "`candidates.ahead_1` is present and is the honest join."},
                "none": {"what": "No stored slot is an honest join; leave ghost dark."},
            },
        ),
        "picture_answered": Noul(
            instructions={
                "question": (
                    "Did the live picture in `picture` respond to this pad act "
                    "(not menu stick-drift or an unanswered huddle)?"
                ),
                "true": "Gameplay picture matches the pad act on the chosen slot.",
                "false": "Menu, no_board, or picture did not answer the pad.",
                "never": "Not authorship. Observation only.",
            },
        ),
        "join_honesty": Score(
            instructions={
                "question": "How honest is this pad-on-this-frame story?",
                "focus": "Rate the join, not capture quality.",
                "never": "Not a license to paint score digits.",
            },
            criteria=[
                "Dishonest — menu, idle pad on a live snap, or empty slots.",
                "Ambiguous — some coupling without a clear answering picture.",
                "Honest — stored HID slot belongs on this HDMI frame.",
            ],
        ),
        "act_kind": Choice(
            instructions={
                "question": "What pad act does the chosen slot most look like?",
                "focus": "Speculative chrome. Ignore when join_id is none.",
                "never": "unknown when unclear. Never infer a score.",
            },
            criteria={
                "snap": {"what": "R2 / snap-like press with snap visual_phase."},
                "sprint": {"what": "Stick heat with running / pursuit picture."},
                "cut": {"what": "Sharp stick change during live play."},
                "menu_stick": {"what": "Stick on menu / select plate / no_board."},
                "idle": {"what": "Idle analog on the chosen slot."},
                "unknown": {"what": "Not enough evidence."},
            },
        ),
    }
