"""Shared pytest fixtures and configuration."""

import os

# Disable the privacy guard during automated tests so unit tests can use
# synthetic / mocked capture devices without a real USB3.0 capture card.
os.environ["QORESENCE_PRIVACY_GUARD"] = "0"
