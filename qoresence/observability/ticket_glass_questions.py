"""TypeSafe questions for TicketGlass v0 (live opt-in glass).

ONE constants module: every question, option set, and gate threshold for the
pack lives here. Question IDs are for code; meaning lives in instructions.

Vote not voice. Compact state + typed questions; code owns consequences.
``licenses_digits`` is False forever. ``board_paint_block`` is VETO-only —
it may force dark / block paint and may never unlock ConfirmTicket digits.
Never replaces scorebug VLM. No Truth-plane wrap.

Patterns: speculative fan-out (one ``system_one`` call) + confidence-gated
routing. Jev is text-only — state never carries pixels.
"""

from __future__ import annotations

from typing import Any

# Choice / Score bands (AGENTS.md observation-plane policy).
CONF_ACT = 0.7
CONF_SOFT = 0.4
# High-stakes Foundry-advisory cut. Glyph only in v0 — no cut side effects.
CONF_CUT = 0.85

# Noul has no separate confidence — use probability.
TITLE_IN_GAME_ACT = 0.7
TITLE_IN_GAME_NOT = 0.3
PAINT_BLOCK_ACT = 0.7
PAINT_BLOCK_NOT = 0.3

MOMENT_CLASSES = (
    "boring",
    "build",
    "clutch",
    "aftermath",
    "unknown",
)

CLIP_NOW = (
    "hold",
    "cut_foundry",
    "extend_window",
)

GLASS_ROUTES = (
    "dark",
    "deck_only",
    "lens",
    "mobile",
    "x_live_overlay",
)

LOCK_STATES = ("blocked", "open", "unknown")
CUT_STATES = ("on", "off")
PAINT_BLOCK_STATES = ("block", "watch", "clear")

TITLE_PLANES = ("in_game", "menu", "pause", "loading", "unknown")
TITLE_PROFILES = ("madden", "cfb", "cod", "other", "unknown")

# Glyph card — three glyphs only; fail-closed if Jev down or low conf.
GLYPHS = ("lock", "tension", "cut")


def ticket_glass_questions() -> dict[str, Any]:
    """One request: title noul + paint veto + moment/clip/route/tension.

    Speculative fan-out: ask every question against the same compact state.
    Code decides which answers to act on. Never mint digits.
    """
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}
    return {
        "title_in_game": Noul(
            instructions={
                "question": (
                    "Is `title.plane` optically in-game right now — a live "
                    "title, not menu, pause, loading, or unknown?"
                ),
                "true": "Optical title is in-game (`title.plane` is in_game, `title.locked`).",
                "false": "Menu, pause, loading, or unknown — not a live in-game title.",
                "never": (
                    "Never licenses score digits. A high noul is a soft gate "
                    "for clip/route only — ConfirmTicket + score_vlm_locked "
                    "remain the only paint path."
                ),
            },
        ),
        "board_paint_block": Noul(
            instructions={
                "question": (
                    "Would painting ticket digits on the live board be "
                    "dishonest right now, given `board.score_vlm_locked`, "
                    "`board.digit_integrity_reason`, and `board.ticket_stale`?"
                ),
                "true": (
                    "Painting ticket digits would misrepresent the live crop "
                    "(stale ticket, crop moved on, menu/plate, no ticket, unlocked)."
                ),
                "false": (
                    "No block signal from this evidence. false is not a paint "
                    "grant — code still owns ConfirmTicket."
                ),
                "never": (
                    "VETO ONLY. true may force dark / block paint. false must "
                    "never unlock, mint, or license digits. Do not restate scores."
                ),
            },
        ),
        "moment_class": Choice(
            instructions={
                "question": (
                    "Given `situation`, `hid`, `outcome.last_events`, and "
                    "`board.ticket_stale`, which moment class is this tick?"
                ),
                "focus": (
                    "Tag the live situation only. Speculative — code maps "
                    "tags to tension; never a highlight or skill claim."
                ),
                "never": "Never invent scores, names, or a Foundry cut.",
            },
            criteria={
                "boring": {"what": "Quiet in-game or idle pad; no build."},
                "build": {"what": "Drive or round is gathering heat; not a peak."},
                "clutch": {
                    "what": "Late/close or red-zone pad+picture density on a live board.",
                    "not_for": "A highlight claim or scoreline.",
                },
                "aftermath": {"what": "Just after a peak; settling, not a new cut."},
                "unknown": {"what": "Not enough licensed evidence to classify."},
            },
        ),
        "clip_now": Choice(
            instructions={
                "question": (
                    "Should Foundry *consider* a local HDMI clip this tick, "
                    "given `foundry`, `title.plane`, `hid`, and `board.ticket_stale`?"
                ),
                "focus": "Advisory only. Code owns the high-stakes cut gate.",
                "never": (
                    "Never cut, export, or arm Foundry. Never a highlight claim. "
                    "Human HOLD beats every PASS. Prefer `hold` when unsure."
                ),
            },
            criteria={
                "hold": {"what": "Do nothing. Default. Ambiguous, menu, or low evidence."},
                "cut_foundry": {
                    "what": "Advisory: consider a local Foundry cut if code's high-stakes gate passes.",
                    "not_for": "A command to cut. Not when `title.plane` is not in-game.",
                },
                "extend_window": {
                    "what": "Keep the current Foundry window open a bit longer.",
                    "not_for": "Starting a new cut.",
                },
            },
        ),
        "lens_tension": Score(
            instructions={
                "question": (
                    "How much Deck/Lens tension should non-digit chrome carry, "
                    "given `hid`, `situation`, and `moment` evidence?"
                ),
                "focus": "Rate observed join density, not capture quality.",
                "never": "Not clutch-as-highlight. Not a scoreline. Not digit paint.",
            },
            criteria=[
                "0 Calm / invisible — no lens chrome.",
                "1 Mild — a hint of presence.",
                "2 Elevated — build or late-drive heat.",
                "3 Peak clutch — pad and picture aligned on a live in-game board.",
            ],
        ),
        "glass_route": Choice(
            instructions={
                "question": (
                    "Which glass may show *non-digit* chrome this tick, given "
                    "`intent`, `title.plane`, and `board.ticket_stale`?"
                ),
                "focus": (
                    "Route chrome only. Digits stay on ConfirmTicket + "
                    "`board.score_vlm_locked`. Ambiguous → `dark`."
                ),
                "never": "Never a digit license. `dark` if menu, unknown, or low evidence.",
            },
            criteria={
                "dark": {"what": "No glass chrome. Fail-closed default."},
                "deck_only": {"what": "Retina Deck may show non-digit chrome."},
                "lens": {"what": "Lens overlay may show non-digit chrome."},
                "mobile": {"what": "Mobile glass may show non-digit chrome."},
                "x_live_overlay": {
                    "what": "X Live overlay may show non-digit chrome (if that glass is already on).",
                    "not_for": "Enabling --x-glass. Not a ship claim.",
                },
            },
        ),
    }
