# Clock Notary — accessible door

Qoresence remains the eyes. QorTroller becomes the notary of the same clock, after the gamer says so.

Gamers reach this the way they reach OBS: Session Theater stays up during the half. The stamp is a door on **Recap**, not a lamp on LIVE.

## Friday-night path

1. Play with `--play --deck`. Open `/session.html`.
2. After the half, Recap → **Export recap**. You get `observation-envelope.json` and a `clock_commitment` hash. Copy the hash.
3. Type your handle. Purpose `portcert` (or `wmp`). Type exactly `I am the gamer`.
4. **Seal this recap**. You get `notary-wrap.json` and a Discord card (session + hash + receipt tail). Chain stays paused.
5. **Verify without trusting us** recomputes the commitment and checks gamer-signed / never-ban / no humanity claim. Producer `status` is ignored.

LIVE Theater cannot light TRUTH. `bridge` / `operator` / protocol names cannot seal.

## HTTP

| method | path | who |
|--------|------|-----|
| GET | `/api/session/clock-notary` | anyone on localhost Deck — export only |
| POST | `/api/session/clock-notary/seal` | gamer phrase + handle |
| POST | `/api/session/clock-notary/verify` | anyone holding the two files |

## CLI

```powershell
python -m qoresence.compose.clock_notary.cli export --recap recap.json --out observation-envelope.json
python -m qoresence.compose.clock_notary.cli wrap --envelope observation-envelope.json --consent consent.json --out notary-wrap.json
```

Sister verifier on QorTroller: `python scripts/clock_notary_verify.py --envelope observation-envelope.json --wrap notary-wrap.json`

## Rails

- Unlocked score digits never serialize.
- Empty DualSense-on-PS5 HID is success.
- Do not merge optical activity into `poep_enabled`.
- PORT-CERT-lite is advisory, never-ban, `humanity_claim: false`.
