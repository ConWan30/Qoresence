# Presence Pack v0 — build receipt

**Branch:** `feat/presence-pack-v0`
**Plane:** `qoresence-observation`
**SKU:** `presence-pack`
**Glass:** Sight Glass Session inner tab `pack` (not a new GAMER_GLASSES item)

## Touched

- `qoresence/compose/clock_notary/presence_pack.py`
- `qoresence/deck/clock_notary_http.py`
- `glass/src/components/session/session-theater.tsx`
- `glass/src/components/session/presence-pack-bay.tsx`
- `glass/src/lib/coupling/clock-notary-api.ts`
- `tests/test_presence_pack.py`
- `glass/scripts/presence-pack-tab.test.ts`

## Routes

- `GET /api/session/clock-notary` — unchanged envelope
- `GET /api/session/presence-pack` — manifest + listing draft
- `GET /api/session/presence-pack.zip` — zip or JSON refuse

Still absent: `/api/session/clock-notary/seal`, `/verify`, wrap dest `qortroller-truth`.

## Click path

`--play --deck` → `http://127.0.0.1:8765/session.html` → tab **pack** → Assemble pack → Download zip → Copy hash.

Recap tab Export still downloads raw envelope JSON.

## Non-goals held

No WMP mint. No autonomous listing. No new gamer glass. Empty HID is not `out_edge`.
