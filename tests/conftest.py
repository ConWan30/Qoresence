"""Shared pytest fixtures and configuration."""

import os

# Disable the privacy guard during automated tests so unit tests can use
# synthetic / mocked capture devices without a real USB3.0 capture card.
os.environ["QORESENCE_PRIVACY_GUARD"] = "0"

# Keep LocalVLM unit tests fast: EasyOCR cold-start is ~50s and would run on
# every 1280x720 synthetic football frame. Scoreboard extractor tests call
# FootballScoreboardExtractor directly and are unaffected.
os.environ.setdefault("QORESENCE_DISABLE_SCOREBOARD_OCR", "1")
