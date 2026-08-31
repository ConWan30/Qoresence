"""--look-graphs / QORESENCE_LOOK_GRAPHS. Default OFF. --play does not enable.

Per-graph env can dark-ship a phase (0/false/off) while the master flag is on.
"""

from __future__ import annotations

import os
from typing import Any

ENV_NAME = "QORESENCE_LOOK_GRAPHS"

# Master ON + unset per-graph env → that graph is on.
# Master ON + per-graph 0/false/off → that graph is dark.
GRAPH_ENVS: dict[str, str] = {
    "ticket_provenance": "QORESENCE_LOOK_TICKET_DAG",
    "crop_evidence": "QORESENCE_LOOK_CROP",
    "same_seq_join": "QORESENCE_LOOK_SAME_SEQ",
    "refuse_chain": "QORESENCE_LOOK_REFUSE",
    "scale_stack": "QORESENCE_LOOK_SCALE",
    "negative_evidence": "QORESENCE_LOOK_NEGATIVE",
}

_FALSE = frozenset({"0", "false", "no", "off"})
_TRUE = frozenset({"1", "true", "yes", "on"})

_config_on = False
_applied_ids: tuple[str, ...] = ()


def set_config_enabled(value: bool) -> None:
    """CLI/config latch. Tests should prefer QORESENCE_LOOK_GRAPHS."""
    global _config_on
    _config_on = bool(value)


def enabled(config: Any | None = None) -> bool:
    env = os.environ.get(ENV_NAME, "").strip().lower()
    env_on = env in _TRUE
    cfg = bool(getattr(config, "look_graphs", False)) if config is not None else _config_on
    return bool(env_on or cfg)


def graph_enabled(graph: str, config: Any | None = None) -> bool:
    if not enabled(config):
        return False
    key = GRAPH_ENVS.get(str(graph or "").strip())
    if not key:
        return True
    raw = os.environ.get(key, "").strip().lower()
    if raw in _FALSE:
        return False
    return True


def note_applied(license_id: str) -> None:
    global _applied_ids
    lid = str(license_id or "").strip()
    if not lid:
        return
    if lid in _applied_ids:
        return
    _applied_ids = (*_applied_ids, lid)


def closeout_applied() -> list[str] | None:
    """Non-breaking closeout key. None when flag off (omit the field)."""
    if not enabled():
        return None
    return list(_applied_ids)


def reset() -> None:
    global _config_on, _applied_ids
    _config_on = False
    _applied_ids = ()
