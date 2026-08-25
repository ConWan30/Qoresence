# Session Theater

Now HUD, Story, Open clip, and Recap for a **normalized** session. Same fail-closed rules as CIVIF: score/yard digits only when the board is locked; button names only when DualSense is bodied on this host.

**Repo doc:** [docs/SESSION_THEATER.md](https://github.com/ConWan30/Qoresence/blob/main/docs/SESSION_THEATER.md)  
**CIVIF history:** [docs/CIVIF.md](https://github.com/ConWan30/Qoresence/blob/main/docs/CIVIF.md)

## Open it

```text
http://127.0.0.1:8765/session.html
```

Live JSON (read-only):

```text
GET http://127.0.0.1:8765/api/session/view
GET http://127.0.0.1:8765/api/session/recap
```

The page polls those APIs only (one timer). It does not fetch `/session_fixtures/*.json`. Allowlisted `?fixture=` still goes through the APIs.

This page is **not** `/deck.html` (HDMI Theater) and **not** `/civif.html`. There is no clip-dock here. Streamer overlay is on hold.

## What you can trust

| Signal | Trust when |
|--------|------------|
| Score / yard digits | Board locked (`LockedValue` after `normalize_pack`) |
| Button / HID names | Controller bodied on this laptop |
| Open clip | `clip.available` and stem `hdmi_clip_<token>` with matching `{stem}.coupling.json` `session_id` |
| Recap counts | Derived from the same normalized events (confirmed / linked clip) |

`freshness.stale` means the last good envelope aged — it is not a fourth content `status`. `ok: false` only for `invalid`.

Keep private by default: qualification/suppression text, unavailable/invalid diagnostics, persist flags, session IDs, internal clocks.

## Shipped on `main`

1. Phase 1–2 foundation — `da0fa95` (#63)
2. Live `GET /api/session/view` — `4ebdf92` (#67, closes #64)
3. Event → existing clip links — `651bb5a` (#70, closes #69)
4. Read-only `GET /api/session/recap` — `27fc4a6` (#73, closes #72)

Docs tips: #66 / #68 / #71 / #74. Tip of this series: `fef4d3c`.

Completed path:

`CIVIF → NarrativeEngine → normalized session view → live Session Theater → validated clip links → read-only session recap`

## Next (not this glass)

- Overlay / streamer presentation — separate milestone after laptop evaluation
- CI full-matrix fail-fast — [#65](https://github.com/ConWan30/Qoresence/issues/65)
- MCP tools `civif_narrative` / `civif_session_view` — not in `tools/list`
