"""TypeSafe questions for the OCCF connector-bind pack (ingress only).

ONE constants module: every question, option set, and gate threshold lives
here. Question IDs are for code; meaning lives in instructions.

Jev only classifies the agent utterance — which closed tool it wants and
what it asks for. Code owns tickets, clocks, digits, bind writes, and MCP
side effects. Confidence is a display axis, never a digit license. The pack
never mints scores, never emits bus events, never takes lobe locks —
``licenses_digits`` is False forever.

Source of truth: ``docs/OCCF.md`` "TypeSafe door (ingress only)".
"""

from __future__ import annotations

from typing import Any

# Noul gate for the three deny rules (OCCF compose: asks_to_* >= 0.6).
NOUL_DENY = 0.6
# Soft gate for affirmative nouls (asks_for_digits / asserts_a_score).
NOUL_SOFT = 0.5
# Compose silent band: low tool confidence or low needs_a_tool_at_all.
TOOL_CONF_MIN = 0.5
NEEDS_TOOL_MIN = 0.3

# Closed tool catalog (OCCF objects -> connector bind -> intent.tool).
TOOLS = (
    "get_observation",
    "get_timeline",
    "request_licensed_clip",
    "export_presence_pack",
    "refuse_actuator",
    "refuse_mid_drive_publish",
    "silent",
)

# Noul names asked in one parallel call (OCCF "TypeSafe door").
NOULS = (
    "asks_for_digits",
    "asks_to_control_pad",
    "asks_to_publish_now",
    "asks_to_leave_localhost",
    "asserts_a_score",
    "needs_a_tool_at_all",
)

# request_risk Score levels (0..2).
RISK_HARMLESS_READ = 0
RISK_LICENSED_SPEECH = 1
RISK_ACTUATOR_OR_EXFIL = 2


def connector_bind_questions() -> dict[str, Any]:
    """One request: tool Choice + six Nouls + request_risk Score."""
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}
    return {
        "tool": Choice(
            instructions={
                "question": (
                    "`turn.utterance` is one agent turn asking about a "
                    "Qoresence play session. Which single tool is it really "
                    "asking for? Pick `silent` when it is just chat."
                ),
                "focus": "Classify the ask only — code owns every side effect.",
                "never": "Never invent a tool outside this catalog.",
            },
            criteria={
                "get_observation": {
                    "what": "Read the live witness pack: what may be said right now."
                },
                "get_timeline": {
                    "what": "Read what happened earlier — drives / chapters / recap tokens."
                },
                "request_licensed_clip": {
                    "what": "Point at a Foundry chapter and ask for the clip."
                },
                "export_presence_pack": {
                    "what": "Take the session with you — leave-the-session zip via the recap door."
                },
                "refuse_actuator": {
                    "what": "Wants to drive the pad / press buttons / make the game do something."
                },
                "refuse_mid_drive_publish": {
                    "what": "Wants to post / publish / stream the live session off-box right now."
                },
                "silent": {"what": "No tool — chat, greeting, or off-topic."},
            },
        ),
        "asks_for_digits": Noul(
            instructions={
                "question": "Does the turn ask for the score / digits / numbers on the board?",
                "true": "It wants score digits (e.g. 'what's the score').",
                "false": "No digit ask.",
                "never": "Never supply digits — code owns speech licensing.",
            },
        ),
        "asks_to_control_pad": Noul(
            instructions={
                "question": (
                    "Does the turn try to control the game — press a button, "
                    "move the pad, make a play happen?"
                ),
                "true": "It wants an actuator effect on the pad / game.",
                "false": "Read-only ask.",
                "never": "The agent never takes the pad — this only labels the ask.",
            },
        ),
        "asks_to_publish_now": Noul(
            instructions={
                "question": (
                    "Does the turn ask to publish / post / stream / share the "
                    "session off this machine right now?"
                ),
                "true": "Mid-session publish or off-box distribution ask.",
                "false": "No publish ask.",
                "never": "Not a license — code denies mid-drive publish.",
            },
        ),
        "asks_to_leave_localhost": Noul(
            instructions={
                "question": (
                    "Does the turn ask to send session data somewhere off "
                    "localhost / LAN — cloud, public URL, remote relay?"
                ),
                "true": "It wants bits to leave the box.",
                "false": "Local ask only.",
                "never": "Localhost pull-only is the default; code owns consent.",
            },
        ),
        "asserts_a_score": Noul(
            instructions={
                "question": (
                    "Does the turn state a score as fact (e.g. 'it's 21-17') "
                    "rather than ask for one?"
                ),
                "true": "It asserts digits.",
                "false": "It asks, or says nothing about a score.",
                "never": "Assertion is never evidence — citation-check vs witness only.",
            },
        ),
        "needs_a_tool_at_all": Noul(
            instructions={
                "question": "Does this turn need any tool, or is it just conversation?",
                "true": "A read / export / deny tool is warranted.",
                "false": "Just chat — no tool.",
                "never": "When unsure, treat as conversation.",
            },
        ),
        "request_risk": Score(
            instructions={
                "question": "How risky is granting this turn what it asks for?",
                "focus": "Rate the ask class, not the agent's politeness.",
                "never": "Risk never licenses digits.",
            },
            criteria=[
                "harmless_read — witness / timeline / policy tokens only.",
                "licensed_speech — wants tokens that need a live ticket (digits, clip).",
                "actuator_or_exfil — pad control, mid-drive publish, off-box send, wrap.",
            ],
        ),
    }
