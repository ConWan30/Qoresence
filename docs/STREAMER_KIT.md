# Qoresence Streamer Kit

Status: **beta, free.** Page: [`docs/streamer-kit.html`](streamer-kit.html) →
<https://conwan30.github.io/Qoresence/streamer-kit.html>. Bundle: [`streamer-kit/`](../streamer-kit/).

The kit packages features that already exist on `main`; it adds no runtime code.

| Feature | Source | Doc |
|---|---|---|
| Verified score overlay (text source set only while locked + capture live) | `qoresence/obs/bridge.py` (`--obs`, `--obs-text-source`) | [OBS_BRIDGE.md](OBS_BRIDGE.md) |
| Auto replay on locked score increase (`SaveReplayBuffer`, ≤1 per 20 s) | same (`--obs-no-replay` to skip) | same |
| Optional scene flash and switch back | `--obs-scene`, `--obs-scene-hold` | same |
| Optional record chapter markers (OBS 30.2+, Hybrid MP4) | `--obs-chapters` | same |
| Optional signed truth feed (hash-chained JSONL, Ed25519 when `[truth]` installed) | `qoresence/truth/`, `--truth-feed`, `/api/truth/feed\|stream\|verify\|pubkey`, `scripts/verify_truth_feed.py` | [TRUTH_FEED.md](TRUTH_FEED.md) |

All talk to OBS over obs-websocket v5 (OBS 28+, port 4455). The password is read from
`QORESENCE_OBS_PASSWORD` only; the kit launcher fills that variable from a secret file
if it is not already set and never stores it.

## Bundle

- `streamer-kit/Qoresence_Streamer_Kit.scene.json`: scene `Qoresence Score` + Text (GDI+) source `Qoresence Score Text`.
- `streamer-kit/qoresence-stream.cmd`: launcher; passes `--obs --obs-text-source "Qoresence Score Text"` (the bridge default `Qoresence Score` would collide with the scene name: OBS error 601).
- `streamer-kit/README.md`: 5-step setup.
- Zip: `python scripts/build_streamer_kit.py` → `dist/qoresence-streamer-kit.zip`. The `Streamer Kit bundle` workflow uploads it as an Actions artifact. No release is published.
- Interest signups: GitHub issue template `streamer_kit_interest.md`. No third-party trackers.

## Honest gaps

- Capture-freeze fix pending a live test on the laptop.
- Truth feed is MVP and not live-tested on the laptop ([TRUTH_FEED.md § Honest gaps](TRUTH_FEED.md#honest-gaps)).
- Scene JSON is hand-written to the OBS scene-collection format and checked by `tests/test_streamer_kit.py`; an actual **Scene Collection → Import** in OBS 28 / 30 / 32 is not yet verified. The text source uses `text_gdiplus_v2` (OBS 30+ may migrate it to v3 on load).
- The `.cmd` launcher has not been run on Windows in CI.
- Madden 27 scorebug reads are what the existing pipeline supports; no new accuracy claim.

---

## Draft sponsor pitch (one-pager) — FOR OWNER REVIEW, NOT SENT

> **Qoresence Streamer Kit — a free, honest score overlay for Madden streamers**
>
> Qoresence watches the HDMI feed locally and only shows a score when it has locked it.
> If it is unsure, the overlay goes blank instead of guessing. On every locked score
> increase it saves an OBS replay and can flash a scene, so streamers get highlight
> clips without touching a hotkey. An optional signed truth feed lets anyone verify the
> locked scores after the stream.
>
> **Why sponsor:** the kit is free and open source. A sponsor credit would sit on the
> kit page and in the bundle README, next to setup gear that the kit actually needs
> (capture card, controller, OBS-friendly hardware).
>
> **What we are not claiming:** no anti-cheat, no audience numbers, no pricing yet.
> The kit is in beta.
>
> **Contact:** qoresence@mail.grokbot.com · <https://conwan30.github.io/Qoresence/streamer-kit.html>

## Plausible sponsor categories (no contact made, none implied)

- HDMI capture cards (the kit needs one)
- Controllers and controller accessories (DualSense / pro-style pads)
- Streaming hardware: stream decks, microphones, webcams, lighting
- Gaming monitors and low-latency HDMI splitters
- Gaming chairs / desks / peripherals
- Streaming platforms or creator tools that integrate with OBS
- Esports / Madden community leagues and tournament organizers
