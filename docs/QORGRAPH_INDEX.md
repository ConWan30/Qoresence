# QORGRAPH — plane-locked loop pack

Compose order on `main`:

1. [`QORGRAPH_DSHOW_VERIFIER.md`](./QORGRAPH_DSHOW_VERIFIER.md) — **landed first** (shared `review:`)
2. [`QORGRAPH_GAME_PROFILE.md`](./QORGRAPH_GAME_PROFILE.md) — `game-profile-pin-holds`
3. [`QORGRAPH_IVC_EMPTY_HID.md`](./QORGRAPH_IVC_EMPTY_HID.md) — `ivc-empty-hid-success`
4. [`QORGRAPH_SESSION_THEATER.md`](./QORGRAPH_SESSION_THEATER.md) — `theater-query-not-capture`
5. [`QORGRAPH_A2A_REENTRANCY.md`](./QORGRAPH_A2A_REENTRANCY.md) — `a2a-reentrancy-default-off`
6. [`QORGRAPH_DECK_LEASE_LAMP.md`](./QORGRAPH_DECK_LEASE_LAMP.md) — `deck-lease-lamp-0.1` (compose after DShow)

**Launcher note:** `qoresence.bat` double-click may add `--a2a`. Python `--play` must stay A2A-off. Society stays leftover. Do not “fix” bat into `--play`. DeckLeaseLamp stays OFF unless `--deck-lease-lamp`.

Pick live pain after the DShow verifier is on disk:

- pin yanked by optics → game profile
- PAD WAIT / heat without ticket → IVC
- Theater growing a grab path → Session Theater
- `age_s` freeze / bat-vs-play A2A confusion → A2A re-entrancy
- Deck looking like a second brain / dual-open temptation → DeckLeaseLamp
