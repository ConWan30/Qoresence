"""Look-license graphs — which look is licensed next.

Observation plane only. Default OFF. Not a second DriveGraph.
"""

from __future__ import annotations

from qoresence.graphs.flags import (
    ENV_NAME,
    GRAPH_ENVS,
    closeout_applied,
    enabled,
    graph_enabled,
    set_config_enabled,
)
from qoresence.graphs.flags import reset as reset_flags
from qoresence.graphs.look_license import LookLicense, make_license


def reset_all() -> None:
    """Clear in-memory graph state. Tests only. Never emits."""
    reset_flags()
    from qoresence.graphs import (
        crop_evidence,
        negative_evidence,
        refuse_chain,
        same_seq_join,
        scale_stack,
        ticket_provenance,
    )

    ticket_provenance.reset()
    crop_evidence.reset()
    same_seq_join.reset()
    refuse_chain.reset()
    scale_stack.reset()
    negative_evidence.reset()


__all__ = [
    "ENV_NAME",
    "GRAPH_ENVS",
    "LookLicense",
    "closeout_applied",
    "enabled",
    "graph_enabled",
    "make_license",
    "reset_all",
    "reset_flags",
    "set_config_enabled",
]
