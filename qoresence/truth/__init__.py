"""Truth feed — append-only, hash-chained stream of locked game facts.

Default OFF (``--truth-feed`` / ``QORESENCE_TRUTH_FEED=1``). See docs/TRUTH_FEED.md.
"""

from qoresence.truth.model import FACT_KINDS, GENESIS_HASH, SCHEMA, TruthFact

__all__ = ["FACT_KINDS", "GENESIS_HASH", "SCHEMA", "TruthFact"]
