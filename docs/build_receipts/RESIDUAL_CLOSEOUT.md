# Residual closeout — roster / DriveGraph cap / wrap / ingredients

Closes the four leftovers that survived title-presence + MCP `get_observation`.

| Residual | Close |
|---|---|
| Roster JSONL / last-name collision | Unique-hit last-name and last+jersey (no team) when the loaded JSONL has exactly one match. Collisions stay `None` + `nameplate_ambiguous`. `collision_report()` + `nameplate_match`. Seasonal dump still operator-synced / gitignored — no invented league file. |
| DriveGraph 48-node hard cap | Named `DEFAULT_MAX_DRIVE_GRAPH_NODES=48`, floor 8, ceiling 96. `QORESENCE_DRIVE_GRAPH_MAX_NODES` / `max_nodes=`. Summary reports `node_cap` / `nodes_truncated` / `raw_node_count`. Still refuses unbounded graphs. |
| Re-wrapping ceremony undeployed | Live dest `qoresence-research`. Hard denylist for `qortroller-truth`. Grant via `QORESENCE_WRAP_GRANT_ID`. MCP `wrap_observation` + auto-wrap on lock when grant is set. Optical record unmutated. |
| Research ingredient ceremony undeployed | `run_research_ceremony` links ingredient `source_hash` to the wrap envelope. Sidecar write stays opt-in (`learning_enabled`). Record not rewritten. |
