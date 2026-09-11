# Clock Notary — accessible door

Qoresence remains the eyes. QorTroller becomes the notary of the same clock, after the gamer says so.

Gamers reach this the way they reach OBS: Session Theater stays up during the half. The **observation export** is a door on **Recap**. Wrap/seal runs in **QorTroller #145** — not as Deck seal APIs.

## Friday-night path

1. Play with `--play --deck`. Open `http://127.0.0.1:8765/session.html`.
2. Recap → **Export recap**. You get `observation-envelope.json` and a `clock_commitment` hash.
3. Seal/wrap on QorTroller (not on this Deck). Chain stays paused until that notary path.

LIVE Theater cannot light TRUTH. Deck never exposes `/seal` or `/verify`.

## HTTP (mounted on Deck — export only)

| method | path |
|--------|------|
| GET | `/api/session/clock-notary` |
| GET | `/session-door.js` |

`create_app()` mounts `mount_clock_notary` for the observation export envelope only. There are **no** Deck seal/verify APIs (`plane=truth` / `wrap_notary` stay off this HTTP surface).

## Rails

- Unlocked score digits never serialize.
- Empty DualSense-on-PS5 HID is success.
- PORT-CERT-lite is advisory, never-ban, `humanity_claim: false` — minted on QorTroller, not Deck.
