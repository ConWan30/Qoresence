# Retina Stem

Situation-directed **session stem** — HDMI + (optional) capture-card audio + DualSense + chapters on one `clock_ns`. Foundry **cuts** from the Stem. Monitor / Deck **look at** the Stem. The Conductor publishes which program the glasses should show. It does **not** switch OBS scenes.

Stem is a glass/lobe on FrameHub and `RetinaEventBus`. It is not a compositor, not a stream client, and not a 1.0 gate.

## What it is

| Piece | Flag | Default |
|-------|------|---------|
| Conductor | rides `--play` | On with play (bus only, no disk) |
| Program-out | `--stem-program` | OFF — implies `--monitor` |
| Audio | `--stem-audio` | OFF — capture-card audio pin only |
| Record | `--stem-record` | OFF — session mux to `clips/stem_*.mp4` |

No `--stem-stream`. No Twitch. No Virtual Cam. No scene stack.

## Why this is not OBS

OBS switches scenes. Stem Conductor emits `stem_program` (`watch` / `prime` / `armed` / `hold` / `encode`) from SituationModel, IVC coupling, companion clip-armed, and clip-busy. Same rules as Theater `director.ts`.

All outputs **subscribe** to FrameHub / ClipBuffer. Program HUD is burned in the Monitor blit only — FrameHub frames stay clean for OCR/VLM.

Audio is a lobe on `clock_ns`, not a mixer. Laptop mics are denied (same privacy spirit as the webcam allow-list).

## Operator

```powershell
# Conductor only (on with play)
python -m qoresence.cli --play --deck --monitor --streamer-fps 60

# Stem Program-out on a second display (no OBS Preview)
python -m qoresence.cli --play --deck --stem-program --stem-program-display 1

# After LIVE is healthy: card audio + optional session record
python -m qoresence.cli --play --deck --stem-audio --stem-record
```

`/health` exposes `stem.mode`, `stem.audio.age_s`, `stem.record.active`.

## Pilot order

1. Capture health, VLM score lock, one local HDMI clip (card in).
2. Conductor + Program-out — this is what makes OBS unused for **ops**.
3. Audio and Record after a real match proves LIVE is healthy.

OBS remains optional only if you still want a platform stream. That is a different product.
