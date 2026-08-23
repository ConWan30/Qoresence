"""Shared pytest fixtures and configuration."""

import os

# Disable the privacy guard during automated tests so unit tests can use
# synthetic / mocked capture devices without a real USB3.0 capture card.
os.environ["QORESENCE_PRIVACY_GUARD"] = "0"

# Keep LocalVLM unit tests fast: EasyOCR cold-start is ~50s and would run on
# every 1280x720 synthetic football frame. Scoreboard extractor tests call
# FootballScoreboardExtractor directly and are unaffected.
os.environ.setdefault("QORESENCE_DISABLE_SCOREBOARD_OCR", "1")


def put_live_coupling_ticket():
    """Mint a live coupling ticket so LicenseGate allows stub A2A cycles."""
    import time

    from qoresence.sync.coupling_ticket import (
        get_coupling_book,
        mint_coupling_ticket,
        reset_coupling_book,
    )

    reset_coupling_book()
    ticket = mint_coupling_ticket(
        clock_ns=time.monotonic_ns(),
        frame_seq=3,
        phrase="SPRINT",
        coupling=0.5,
        hold_energy=1.0,
        pll_lock=True,
        video_fresh=True,
    )
    get_coupling_book().put(ticket)
    return ticket
