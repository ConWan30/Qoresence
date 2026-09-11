# Clock Notary — accessible door

Qoresence remains the eyes. QorTroller becomes the notary of the same clock, after the gamer says so.

Gamers reach this the way they reach OBS: Session Theater stays up during the half. The stamp is a door on **Recap**, not a lamp on LIVE.

## Friday-night path

1. Play with `--play --deck`. Open `http://127.0.0.1:8765/session.html`.
2. Recap → **Export recap**. You get `observation-envelope.json` and a `clock_commitment` hash.
3. Type your handle. Purpose `portcert` (or `wmp`). Type exactly `I am the gamer`.
4. **Seal this recap**. You get `notary-wrap.json` and a Discord card. Chain stays paused.
5. **Verify without trusting us**, or:

```powershell
python scripts/clock_notary_verify.py --envelope observation-envelope.json --wrap notary-wrap.json
```

(from the QorTroller checkout)

LIVE Theater cannot light TRUTH. `bridge` / `operator` / protocol names cannot seal.

## HTTP (mounted on Deck)

| method | path |
|--------|------|
| GET | `/api/session/clock-notary` |
| POST | `/api/session/clock-notary/seal` |
| POST | `/api/session/clock-notary/verify` |
| GET | `/session-door.js` |

`create_app()` wraps the canonical Deck server and calls `mount_clock_notary`.

## Rails

- Unlocked score digits never serialize.
- Empty DualSense-on-PS5 HID is success.
- PORT-CERT-lite is advisory, never-ban, `humanity_claim: false`.
