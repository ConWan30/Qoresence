"""
ClutchBot — game-state-aware Twitch agent for Qoresence.

Consumes Qoresence bus events, builds a rolling situation model, scores
narrative moments, and dispatches actions (chat messages, clips, predictions)
to pluggable backends.
"""
