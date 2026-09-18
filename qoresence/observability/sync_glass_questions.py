"""TypeSafe questions for SyncGlass v0 (pad↔picture bind glass).

ONE constants module: every question, option set, and gate threshold for the
pack lives here. Question IDs are for code; meaning lives in instructions.

Vote not voice. Compact state + typed questions; code owns consequences.
``licenses_digits`` is False forever. v0 is advisory + glyphs + ``/health``
only — code must never apply ``lag_center`` recenter or change capture fps
from Jev alone.

DualSense topology (immutable): USB on the laptop is *observe*; BT on the
PS5 is *play*. Equalize via video-clock bind facts
(``syncLagMs`` / ``hidAt`` / ``lag_center_ms``) — never by deleting USB
physics. No Truth-plane / QorTroller wrap. No haptic authorship.
"""

from __future__ import annotations

from typing import Any

# Choice / Score bands (AGENTS.md observation-plane policy).
CONF_ACT = 0.7
CONF_SOFT = 0.4
# High-stakes pacing advisory. Glyph + health only in v0 — never applied.
CONF_RECENTER = 0.85

# Noul has no separate confidence — use probability.
BIND_HEALTHY_ACT = 0.7
BIND_HEALTHY_NOT = 0.3
HAPTIC_COUPLED_ACT = 0.7
HAPTIC_COUPLED_NOT = 0.3

LAG_CLASSES = (
    "ok",
    "pad_ahead",
    "picture_ahead",
    "hid_empty_usb",
    "capture_starve",
    "unknown",
)

ACTIONS = (
    "observe",
    "recenter_soft",
    "flag_operator",
    "dark_overlay",
)

BIND_STATES = ("ok", "soft", "off", "unknown")
HAPTIC_STATES = ("on", "off", "unknown")
HID_SOURCES = ("usb_play", "bt", "empty")

# Glyph card — three glyphs only; fail-closed if Jev down or low conf.
GLYPHS = ("bind", "lag", "haptic")


def sync_glass_questions() -> dict[str, Any]:
    """One request: bind noul + lag class + haptic noul + action + severity.

    Speculative fan-out: ask every question against the same compact state.
    Code decides which answers to surface. Never mint digits. Never retune
    capture fps or ``lag_center`` from these answers in v0.
    """
    try:
        from typesafe_sdk import Choice, Noul, Score
    except Exception:
        return {}
    return {
        "bind_healthy": Noul(
            instructions={
                "question": (
                    "Do pad and picture co-occur on the video clock right now, "
                    "given `hid` bind facts (`sync_lag_ms`, `hid_at_ns`, "
                    "`lag_center_ms`) and `video` freshness / `pll_lock`?"
                ),
                "true": (
                    "USB-observe pad edges (or honest Path-B empty HID with "
                    "fresh picture) join the HDMI clock in-band."
                ),
                "false": (
                    "Pad and picture do not co-occur: empty USB with no "
                    "picture bind, capture starve, or lag far outside "
                    "`lag_center_ms`."
                ),
                "never": (
                    "Never licenses score digits. Never a command to retune "
                    "lag_center or capture fps. DualSense USB is laptop "
                    "observe; BT on the PS5 is play — do not treat empty "
                    "laptop HID as a dead capture card."
                ),
            },
        ),
        "lag_class": Choice(
            instructions={
                "question": (
                    "Which single lag class best describes `hid` vs `video` "
                    "on the video clock this tick?"
                ),
                "focus": (
                    "Classify bind facts only. Code owns clocks, PLL, and "
                    "any later operator GO. Path B (laptop HID empty, DualSense "
                    "on PS5) is `hid_empty_usb`, not a capture death."
                ),
                "never": (
                    "Never prescribe a fps change or lag_center write. "
                    "Never mint digits. Never author haptics."
                ),
            },
            criteria={
                "ok": {
                    "what": (
                        "Bind facts in band: pad and picture co-occur near "
                        "`lag_center_ms` on a fresh video clock."
                    ),
                },
                "pad_ahead": {
                    "what": (
                        "HID/pad stamps lead the picture they should join "
                        "(sync_lag below center / negative skew)."
                    ),
                    "not_for": "Empty laptop HID (that is hid_empty_usb).",
                },
                "picture_ahead": {
                    "what": (
                        "Picture/video clock leads the pad they should join "
                        "(sync_lag above center / HDMI delay grown)."
                    ),
                    "not_for": "A frozen grab loop (that is capture_starve).",
                },
                "hid_empty_usb": {
                    "what": (
                        "Laptop USB HID is empty. Default live topology: "
                        "DualSense stays on the PS5 over BT; this host only "
                        "observes. Honest Path B — not a capture failure."
                    ),
                    "not_for": "A reason to drop capture fps or unplug USB physics.",
                },
                "capture_starve": {
                    "what": (
                        "`video.age_s` climbing and/or `capture.starve` — "
                        "frames stalled. Grab waits for nobody; this is "
                        "observation of starve, not a grab-loop fix."
                    ),
                },
                "unknown": {"what": "Not enough video-clock bind facts to classify."},
            },
        ),
        "haptic_coupled": Noul(
            instructions={
                "question": (
                    "Does vibration co-occur with picture/outcome this tick, "
                    "given `haptic.co_occur_recent` and `haptic.probe_ok`? "
                    "`probe_ok` is null unless `--haptic-probe` / "
                    "`QORESENCE_HAPTIC_PROBE=1` started the private probe. "
                    "`co_occur_recent` is true when a recent `imu_echo` or "
                    "`hid_output` pulse joined the video clock (EchoDetector "
                    "on USB IMU — not PS5 BT output rumble mirrored on USB)."
                ),
                "true": (
                    "A probe-backed haptic pulse (`imu_echo` / `hid_output`) "
                    "co-occurred with picture/outcome on the video clock."
                ),
                "false": (
                    "No co-occurrence, probe off (`probe_ok` null), probe "
                    "down, stick-only motion, or channel unavailable."
                ),
                "never": (
                    "Observe only. Never author rumble, THROW, or a haptic "
                    "signature. Never a cheat/eligibility claim. Vote not "
                    "voice — do not invent digits or unlock score."
                ),
            },
        ),
        "action": Choice(
            instructions={
                "question": (
                    "Which advisory action should glass/health surface this "
                    "tick, given `lag_class`, `bind_healthy`, and `capture`?"
                ),
                "focus": (
                    "Advisory only. v0 code never applies recenter or fps. "
                    "Ambiguous → `observe`. Jev down / no facts → `dark_overlay`."
                ),
                "never": (
                    "Never a command to write lag_center, change capture fps, "
                    "author haptics, or mint digits. Human HOLD / operator GO "
                    "owns any later pacing change."
                ),
            },
            criteria={
                "observe": {
                    "what": (
                        "Default. Path-B empty HID, in-band bind, or not enough evidence to flag."
                    ),
                },
                "recenter_soft": {
                    "what": (
                        "Advisory: consider a lag_center nudge if code's "
                        "high-stakes gate (conf≥0.85) would pass."
                    ),
                    "not_for": ("A command to apply PLL recenter. v0 still glyphs + health only."),
                },
                "flag_operator": {
                    "what": (
                        "Capture starve or a pad/picture split that needs a "
                        "human glance. Not a silent retune."
                    ),
                },
                "dark_overlay": {
                    "what": "Fail-closed. Unknown, no key, or no bind facts.",
                },
            },
        ),
        "severity": Score(
            instructions={
                "question": (
                    "How severe is the pad↔picture skew this tick, given "
                    "`hid.sync_lag_ms`, `hid.lag_center_ms`, and `video.age_s`?"
                ),
                "focus": "Rate observed bind facts, not capture-card quality.",
                "never": "Not a fps command. Not a digit. Not haptic authorship.",
            },
            criteria=[
                "0 In band — pad and picture agree on the video clock.",
                "1 Mild skew — noticeable but playable; Path-B empty HID is at most this.",
                "2 Elevated skew — bind facts disagree; operator may want a glance.",
                "3 Severe — capture starve or a pad/picture split that needs an operator.",
            ],
        ),
    }
