"""Football visual_phase vocabulary — shared allowlist and transition graph."""

from __future__ import annotations

VISUAL_PHASES = frozenset(
    {
        "huddle_offense",
        "huddle_defense",
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

ACTIVE_PHASES = frozenset(
    {
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

BOUNDARY_PHASES = frozenset({"huddle_offense", "huddle_defense"})

BOUNDARY_GAME_STATES = frozenset({"replay", "results", "menu", "paused"})

# Snap is preplay only — never opens a candidate interval.
PREPLAY_PHASES = frozenset({"snap"})

MOMENT_BOUNDARY_TIMEOUT_NS = 30_000_000_000

VALID_TRANSITIONS: dict[str, frozenset[str]] = {
    "huddle_offense": frozenset({"snap", "running", "passing"}),
    "huddle_defense": frozenset({"snap", "coverage", "defense_pursuit"}),
    "snap": ACTIVE_PHASES,
    "running": ACTIVE_PHASES | BOUNDARY_PHASES,
    "passing": ACTIVE_PHASES | BOUNDARY_PHASES | frozenset({"ball_in_air"}),
    "ball_in_air": ACTIVE_PHASES | BOUNDARY_PHASES,
    "coverage": ACTIVE_PHASES | BOUNDARY_PHASES,
    "defense_pursuit": ACTIVE_PHASES | BOUNDARY_PHASES,
    "defense_engaged": ACTIVE_PHASES | BOUNDARY_PHASES,
    "blocking": ACTIVE_PHASES | BOUNDARY_PHASES,
    "player_locked_receiver": ACTIVE_PHASES | BOUNDARY_PHASES,
}
