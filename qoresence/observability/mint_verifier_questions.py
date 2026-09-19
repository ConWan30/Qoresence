"""TypeSafe questions for the mint-verifier pack.

ONE constants module: every question, option set, and gate threshold lives
here. Question IDs are for code; meaning lives in instructions.

The pack judges a licensed ConfirmTicket against the live VLM parse and
names a next act (hold / remint / blank / observe). It never mints scores,
never emits bus events, never takes lobe locks — ``licenses_digits`` is
False forever.
"""

from __future__ import annotations

from typing import Any

CONF_ACT = 0.7
CONF_SOFT = 0.4

HUD_KINDS = (
    "live_hud",
    "preplay",
    "select_plate",
    "menu",
    "loading",
    "no_board",
)

ACTIONS = ("hold", "remint", "blank", "observe")

BLANK_HUD = frozenset({"menu", "select_plate", "loading"})

DETERMINISTIC_REFUSE = frozenset(
    {
        "implausible_transition",
        "refuse_implausible",
        "refuse_zero_zero",
        "empty_crop_hash",
        "identity_swap",
        "refuse_identity_swap",
        "refuse_suspicious",
    }
)


def mint_verifier_questions() -> dict[str, Any]:
    """One request: identity + scorebug + pair + speculative legal delta + HUD."""
    try:
        from typesafe_sdk import Choice, Noul
    except Exception:
        return {}
    return {
        "same_game": Noul(
            instructions={
                "question": (
                    "Does `live` describe the same match identity as `ticket` "
                    "(same teams / wordmarks)?"
                ),
                "true": "Live parse is the same game the ticket licensed.",
                "false": "Different matchup, or live has no identity to compare.",
                "never": "Not a digit check — code owns exact score equality.",
            },
        ),
        "scorebug_in_crop": Noul(
            instructions={
                "question": (
                    "Does `live` describe a live in-game or preplay scorebug, "
                    "not a menu, pause plate, or empty crop?"
                ),
                "true": "Live HUD or preplay stick HUD with match identity.",
                "false": "Menu, select plate, loading, empty, or no_board.",
                "never": "Not a license to paint — observation only.",
            },
        ),
        "pair_matches_ticket": Noul(
            instructions={
                "question": (
                    "Does the live home/away pair equal the licensed ticket pair "
                    "(`ticket.home_score` / `ticket.away_score`)?"
                ),
                "true": "Same integers as the ticket.",
                "false": "Different pair, or live pair is missing.",
                "never": "Never invent a pair. Compare the supplied integers only.",
            },
        ),
        "legal_transition": Noul(
            instructions={
                "question": (
                    "Assuming the live pair differs from the ticket: is the "
                    "delta a one-team football scoring increment "
                    "(1, 2, 3, 6, 7, or 8 points) listed in `policy.football_deltas`?"
                ),
                "true": "One side moved by a legal increment; the other stayed.",
                "false": "Drop, both sides moved, OCR echo (e.g. 7-0 → 20-20), or no delta.",
                "never": "Speculative — code ignores this unless the pairs differ.",
            },
        ),
        "hud_kind": Choice(
            instructions={
                "question": "Which HUD scene is `live` most like?",
                "focus": "Classify the live crop; code still owns digit licensing.",
                "never": "no_board when nothing usable is in the crop.",
            },
            criteria={
                "live_hud": {"what": "In-game scorebug during a snap or play."},
                "preplay": {"what": "Play-call / Subs / audible stick HUD with wordmarks."},
                "select_plate": {"what": "Pause SELECT plate that invents a score pair."},
                "menu": {"what": "Main menu, lobby, or results."},
                "loading": {"what": "Loading, cutscene, or replay."},
                "no_board": {"what": "No usable board in the crop."},
            },
        ),
    }
