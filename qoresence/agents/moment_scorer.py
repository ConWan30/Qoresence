"""
MomentScorer for ClutchBot.

Decides whether the current situation is worth a chat message, clip,
prediction, or other action. Phase 1 is rule- and template-driven. The design
is intentionally modular so a small LLM or learned scorer can be swapped in
later.
"""
