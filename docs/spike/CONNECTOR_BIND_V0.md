# Connector Bind v0 — OCCF slice 2

Source of truth: `docs/OCCF.md` (objects → connector bind; correlation
states; synchronization methods; TypeSafe door; land order #3). Landed on
`feat/occf-connector-bind` after `jev.ledger.v0` (`#245`).

## What landed

- `qoresence/observability/connector_bind.py` — builds or refuses one
  `qoresence.connector-bind.v0` row per agent turn (accept **and** refuse).
  `ConnectorBind` is a synchronous pull-only engine: no bus subscription,
  no worker thread, no lobe locks, no pad ownership.
- `qoresence/observability/connector_bind_questions.py` — TypeSafe door:
  one parallel ask (tool Choice + six Nouls + `request_risk` Score).
  Code owns compose; Jev only classifies. Deterministic local-heuristic
  fallback when the SDK/key is absent.
- Flag/env: `--jev-connector` / `QORESENCE_JEV_CONNECTOR=1`, plus
  `JevConnectorConfig` (`seq_match_window`, `typesafe_timeout_s`).
  Default OFF; `--play` does not enable it.
- Binds are written **only** through the unified Jev ledger as
  `pack="connector"` (`note_judgment`). There is no `connector.jsonl` —
  the connector flag implies a ledger write for these rows (cli startup
  ORs `jev_connector.enabled` into `configure_jev_ledger`, and the engine
  ensures the ledger when enabled via env).

## Correlation states (OCCF)

`bound` / `unbound` / `stale` / `denied`. Sync is first-match, fail-closed:

| Method | When | Copied onto the bind |
|---|---|---|
| `live_pull` | session live + FrameHub frame + `get_observation` | current `clock_ns`, `frame_seq`, witness hash |
| `seq_match` | agent echoes `frame_seq` | that seq if in `seq_match_window`; else `stale` |
| `chapter_id` | agent names a supplied chapter | chapter `t0_clock_ns` |
| `recap_door` | session ended / recap open | envelope `clock_commitment` |
| `none` | otherwise | `unbound` |

`stale` also fires when a live_pull/seq_match bind lands while
`ticket_stale` facts say the confirm drifted (`last_confirm=present` +
stale class). There is no `muse_vm_time`, `wall_clock_guess`,
`pad_event_id`, or `sync_glass_bind` method: `agent.asked_at_unix_ms` is
guest annotation and never stamps `observatory.clock_ns` (`clock_ns = 0`
is legal — the turn is not on the video clock).

## Deny reasons (closed set)

`pad_not_on_this_plane`, `mid_drive`, `localhost_only`,
`actuator_or_exfil`, `off_plane_wrap`. Compose order follows OCCF: pad →
mid-drive publish → leave-localhost → silent band (`tool_confidence < 0.5`
or `needs_a_tool_at_all < 0.3`) → `request_risk == 2`. Deterministic
preflight refuses (pad-command payloads, off-plane wrap dests like
`qortroller-truth`) deny with `source="preflight"` before classification.

## Forbidden on the row

Score integers, ticket bodies, crop pixels, API keys, Muse memory files,
HDMI JPEGs, DualSense reports, Recap envelope blobs. An asserted score in
the utterance is never serialized — `asserts_a_score` is a noul float,
and speech stays `boxes` without a present confirm. `licenses_digits` is
`false` forever.

## Deferred (OCCF land order)

- Live ingress callers (Muse MCP skill / tinkabot slice 3) — they
  scaffold `get_observation`; `note_agent_turn(turn, observatory=...)` is
  the bind entry point for later correlation.
- Optional `jev_tail` on `get_observation` (pack/action/source tokens).
- Pages / directory listing.
- Migrating packs off private JSONL.
