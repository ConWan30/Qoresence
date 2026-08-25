# Session Theater

Local operator glass for a **normalized** session: Now HUD, Story, Open clip, and Recap. Observation plane only. DualSense often stays on the PS5 — empty HID and no button names unless the pad is bodied on this host. Score and yard digits render only when the board is locked.

Canonical path on `main` (docs tip **`fef4d3c`**, recap code **`27fc4a6`**):

`CIVIF → NarrativeEngine → normalized session view → live Session Theater → validated clip links → read-only session recap`

This is **not** HDMI Theater (`/deck.html`), not `/civif.html` play-by-play, and not an OBS overlay. Streamer presentation stays on hold until real play proves a repeated broadcast use case. A later overlay is a **separate** milestone and must consume the existing view/recap contracts only.

Full CIVIF history: [CIVIF.md](CIVIF.md). Wiki: [Session-Theater](wiki/Session-Theater.md).

## Current state

| Surface | Role |
|---------|------|
| `/session.html` | Now + Story + Recap. Gamer / Analyst share one normalized view. |
| `GET /api/session/view` | Live envelope (`session-view-1` inside `view`). |
| `GET /api/session/recap` | Flat `session-recap-1` derived from that same model. |
| Story **Open clip** | Only when a validated existing clip is linked. |
| `?fixture=` | Allowlisted fixtures through the **same** APIs (no client fetch of `/session_fixtures/*.json`). |

**Private by default** (do not treat as broadcast copy): qualification and suppression reasons, unavailable/invalid diagnostics, persist/logging flags, detailed coach context, session IDs, internal clocks, hidden input or system behavior.

**Evaluation hold:** no new streamer overlay, no new telemetry or clip ID format, no `/civif.html` rewrite, no MCP `civif_narrative` / `civif_session_view` / `export_clip`. Laptop pilots evaluate Story, Clips, Recap, Trust, Broadcast suitability, and Reliability on the operator box (this cloud VM has no capture card).

## Operator usage

With Deck up (`--play --deck` or equivalent):

```text
http://127.0.0.1:8765/session.html
http://127.0.0.1:8765/api/session/view
http://127.0.0.1:8765/api/session/recap
```

Optional: `?session_id=` or `?fixture=<allowlisted-name>` on both APIs and the page.

The client uses **one** `tickAll` timer: fetch view, then recap. Do not point the browser at raw fixture JSON.

### View envelope

`ok`, `status`, `session`, `view`, `freshness.{generated_at,last_event_at,age_ms,stale}`

| `status` | Meaning |
|----------|---------|
| `live` | Usable normalized session |
| `empty` | Persisted empty pack |
| `not_persisted` | No persisted narrative yet |
| `unavailable` | Missing session/fixture |
| `invalid` | Rejected source; `ok` is `false` only here |

`stale` is freshness only. Aged last-good content keeps its `status` (for example `live`) with `freshness.stale: true`. Live generate uses `persist=False`. HTTP stays 200; routes do not 500 on malformed packs.

### Recap envelope (`session-recap-1`)

Public fields: `schema`, `ok`, `status`, `session`, `duration_ms`, `event_count`, `confirmed_event_count`, `linked_clip_count`, `incomplete`, `empty_reason`, `events`, `freshness`.

- `duration_ms` from usable clocks (`> 0`, both present, `end >= start`); `null` if none; equal nonzero start/end may be `0`; never negative.
- `event_count` = listed events; confirmed = `qualification === "confirmed"`; linked = `clip.available === true`.
- Order: usable `t_start_ns` first, then original index.
- `empty_reason` only for `empty` / `not_persisted`.
- `incomplete` only for `live` + `persisted == false`.
- Invalid: empty events, safe freshness, no raw packs.
- Derived from `build_session_response` / `recap_from_envelope` — no persist, no clip re-resolve.

### Clip contract (existing media only)

- Stem: `hdmi_clip_<token>`
- URL: `/media/clips/{stem}.mp4`
- Session membership: `{stem}.coupling.json` `session_id` must be a non-empty string equal to the view session
- Normalized event: `clip: {available, clip_id?}` — raw `evidence.clip_ids` are not leaked
- Paths, `%`, NUL, aliases (`hdmi_a`), missing files, cross-session, int/empty sidecar session → `{available: false}`
- **Open clip** only if `available` and the stem matches. No clip-dock on `/session.html`.

## Shipped milestones

| Milestone | `main` SHA | PR | Issue |
|-----------|------------|----|-------|
| Phase 1–2 foundation | `da0fa95` | [#63](https://github.com/ConWan30/Qoresence/pull/63) | — |
| Phase 1–2 docs | `85e104a` | [#66](https://github.com/ConWan30/Qoresence/pull/66) | — |
| Phase 3 `GET /api/session/view` | `4ebdf92` | [#67](https://github.com/ConWan30/Qoresence/pull/67) | [#64](https://github.com/ConWan30/Qoresence/issues/64) |
| Phase 3 docs | `769c168` | [#68](https://github.com/ConWan30/Qoresence/pull/68) | — |
| Event → clip linkage | `651bb5a` | [#70](https://github.com/ConWan30/Qoresence/pull/70) | [#69](https://github.com/ConWan30/Qoresence/issues/69) |
| Clip-link docs | `fbba093` | [#71](https://github.com/ConWan30/Qoresence/pull/71) | — |
| `GET /api/session/recap` | `27fc4a6` | [#73](https://github.com/ConWan30/Qoresence/pull/73) | [#72](https://github.com/ConWan30/Qoresence/issues/72) |
| Recap docs | `fef4d3c` | [#74](https://github.com/ConWan30/Qoresence/pull/74) | — |

### Phase 1–2 (`da0fa95`)

Fail-closed `session_view.normalize_pack`, `LockedValue` score/yard, bodied-only HID names, Now + Story, Gamer/Analyst, persisted vs not-persisted empty states, allowlisted fixtures, no route 500 on malformed packs.

**Excluded at merge; landed later:** live view API (#67), recap (#73). Still excluded: clip-dock on this page, HDMI Theater, `/civif.html`, MCP `tools/list`.

### Phase 3 (`4ebdf92`)

Read-only view envelope; `stale` is not a `status`; `/session.html` polls the API only.

**Excluded at merge; landed later:** recap (#73). Still excluded: clip-dock, HDMI Theater, `/civif.html`, MCP listing, NarrativeEngine persist-path change, CI fail-fast [#65](https://github.com/ConWan30/Qoresence/issues/65).

### Clip linkage (`651bb5a`)

Trusted event opens existing reviewable MP4s only. Stale envelopes keep already-validated `clip` objects.

**Excluded at merge; landed later:** recap (#73). Still excluded: clip-dock, new clip IDs, `/civif.html`, MCP, NarrativeEngine gating, #65.

### Recap (`27fc4a6`)

Flat `session-recap-1`. One `tickAll` timer. Chromium smoke: zero `/session_fixtures/` requests.

**Still excluded:** streamer overlay (separate later milestone), clip-dock, HDMI/capture redesign, `/civif.html`, MCP `tools/list`, NarrativeEngine changes, #65.

## Tests

- `tests/test_session_theater.py`
- `tests/test_session_clip_link.py`
- `tests/test_session_recap.py`

Do not mix [#65](https://github.com/ConWan30/Qoresence/issues/65) full-matrix `pytest tests/ -x` into Session Theater work without new evidence.
