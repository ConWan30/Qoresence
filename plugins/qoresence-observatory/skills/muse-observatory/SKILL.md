---
name: muse-observatory
description: >
  Ask a local Qoresence session what may be said right now. Pull-only
  observatory connector (OCCF): one witness read, get_observation, plus two
  closed refuse tools. Use when the person asks about the live game, the
  board, or the session. Never for controlling the pad, the capture, or
  publishing. Triggers: qoresence, observation, witness, live game, score,
  OCCF, observatory.
---

# Muse × Qoresence observatory

Muse is a **guest clock**. You bring the agent turn; Qoresence owns capture,
`clock_ns`, tickets, and fail-closed speech. You may *ask about* a play
session. You may never drive it.

Plane `qoresence-observation`. `licenses_digits=false` forever.

## Connect

Stdio MCP on the gamer's machine. Point your MCP config at
`plugins/qoresence-observatory/mcp.json`, or launch directly:

```bash
QORESENCE_OCCF=1 python -m qoresence.mcp.occf        # stdio, speaks JSON-RPC
qoresence-occf-mcp --occf                          # console-script equivalent
```

Without `QORESENCE_OCCF=1` (or `--occf`) the server answers `initialize` with
`occf.enabled=false`, lists zero tools, and fails every `tools/call` closed.
`--play` never enables it — this is opt-in only.

For `get_observation` to see a live session, Qoresence must be running on the
same host with `--agent-glass` (loopback `127.0.0.1:8765`). If it is not, the
tool returns blanks — that is the correct answer, not an error to work around.

Optional envs on the MCP process: `QORESENCE_JEV_LEDGER=1` lets `jev_tail`
read token-only rows from `logs/jev_ledger.jsonl`
(`QORESENCE_JEV_LEDGER_PATH` overrides); `QORESENCE_JEV_CONNECTOR=1` lets an
`agent_turn` argument compose and record a `pack="connector"` bind row.
Both stay opt-in — without them the answers are fail-closed empties.

## Tools (the whole catalog)

| Tool | Use |
|---|---|
| `get_observation` | Call **before speaking** about the session. Returns the witness pack: `title`, `score`, `pad`, `glass`, `clock_ns`/`seq`, `may_say`, `must_not_invent`. Optional `jev_tail` (0–20) appends token-only Jev ledger rows (`pack`/`action`/`source`/`state`/`clock_ns`) when the ledger is enabled. Optional `agent_turn` correlates your ask to an observatory instant (see below). |
| `refuse_actuator` | The person asked you to press, move, own the pad/DualSense, or control capture. Call this. It answers `deny_reason=pad_not_on_this_plane`. No side effects. |
| `refuse_mid_drive_publish` | The person asked you to post, share, upload, or clip-to-public during play. Call this. It answers `deny_reason=mid_drive_publish`. No side effects. |

### Correlating your turn (`agent_turn`)

Pass `agent_turn` on `get_observation` to bind your ask to the observatory
clock — the OCCF connector-bind path (`--jev-connector` /
`QORESENCE_JEV_CONNECTOR=1`, landed as `qoresence.connector-bind.v0` rows on
the Jev ledger as `pack="connector"`):

```json
{"agent_turn": {"brand": "muse", "turn_id": "t-41",
                "asked_at_unix_ms": 1758294000000,
                "utterance": "what's happening right now"}}
```

The response gains a `bind` block: `state` (`bound`/`unbound`/`stale`/
`denied`), `method`, `deny_reason`, `speech`, `bind_id`, `recorded`.

- `bound` is only ever reported when a `pack="connector"` row was actually
  written (connector on **and** a `session_id` known). Otherwise the honest
  answer is `unbound` — your turn is not on the video clock; do not narrate
  the game as if it were.
- `deny_reason` is always binding — even unrecorded. Honor it; never soften
  a deny into a tool call.
- `asked_at_unix_ms` is guest annotation only. It never stamps
  `observatory.clock_ns` — `clock_ns` comes back from the observatory or
  stays `0`.
- `session_id` you may echo from a prior bind or the operator. `bind` rows
  containing score integers, ticket bodies, pixels, or pad reports do not
  exist — do not send them.

There is no `get_timeline`, `export_presence_pack`, `search_clips`, frame, or
write tool on this server. If a request needs one, it is out of scope for
v0 — say so; do not invent a tool name.

## Speech contract

- Speak only items in `may_say`, in your own words. Everything in
  `must_not_invent` is a silence list — never fill it by guessing.
- **Digits:** `score.claim` tells you whether a confirmed score exists on the
  board. `home`/`away` are always `null` on this plane — the connector never
  mints or echoes score digits, even when licensed. You may say "the score is
  confirmed on the board"; you may never say the numbers.
- `score.claim=false` → the board is `□–□`. Say so or stay silent.
- `glass.url` with `lan=false` is localhost-only — do not tell anyone to open
  it on a phone. `lan=true` means same Wi-Fi, never a public stream.
- `jev_tail` rows are observability tokens, not facts about the game. Cite
  `pack`/`action`; never narrate them as play-by-play.
- When the whole pack is blank (`must_not_invent` holds `no_live_session` /
  `no_observation` / `occf_disabled`), the honest answer is "no live session
  is visible to me." A blank is a verdict, not a missing feature.

## Never

- Pad input, DualSense, capture control, hike/queue — `refuse_actuator`.
- Mid-drive publish to anywhere — `refuse_mid_drive_publish`.
- Score integers, ticket bodies, crop pixels, HDMI frames as authority.
- Your own clock stamped as `clock_ns`. Observatory time comes back in the
  pack; if it is `null`, the turn is not on the video clock.
- SyncGlass pad↔picture "healthy" is not a licensed board. Empty laptop HID
  is success, not a disconnected controller.

Correlate three clocks. Merge none.
