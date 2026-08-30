# CIVIF — Coupled Input–Video Intelligence Framework

Observation plane only. Qoresence does **not** claim legitimacy, eligibility, or anti-cheat. DualSense often stays on the PS5; the laptop may never see HID.

## Overview

CIVIF is the **live + clip observation** layer:

- **Coupled Event Record** is the primitive (clip sidecars `civif-v0`, live ticks `civif_tick-1`).
- Highlights, coaches, search, and narrative are **queries** over those records.
- Theater LIVE (`/live.jpg`) is unchanged. Open `/civif.html` for CIVIF (JSON ~1 Hz).
- Session Theater (`/session.html`) is a separate Now + Story + Recap glass over the normalized narrative pack. Operator contract: [SESSION_THEATER.md](SESSION_THEATER.md).

## Current shipped state (Session Theater)

On `main` through recap docs **`fef4d3c`** (code **`27fc4a6`**):

`CIVIF → NarrativeEngine → normalized session view → live Session Theater → validated clip links → read-only session recap`

| Milestone | SHA | PR |
|-----------|-----|----|
| Phase 1–2 foundation | `da0fa95` | [#63](https://github.com/ConWan30/Qoresence/pull/63) |
| Live `GET /api/session/view` | `4ebdf92` | [#67](https://github.com/ConWan30/Qoresence/pull/67) |
| Event → clip linkage | `651bb5a` | [#70](https://github.com/ConWan30/Qoresence/pull/70) |
| `GET /api/session/recap` | `27fc4a6` | [#73](https://github.com/ConWan30/Qoresence/pull/73) |

Hold streamer overlay until laptop play proves a repeated broadcast use case. Overlay later is a **separate** milestone. Historical “Excluded” lists below are **as of that merge**; later rows landed in later PRs (see [SESSION_THEATER.md](SESSION_THEATER.md)).
