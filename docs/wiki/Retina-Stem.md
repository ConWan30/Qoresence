# Retina Stem

Situation-directed **session stem**. Not OBS.

A stem is one timeline with grouped tracks. Qoresence’s stem is HDMI + (optional) capture-card audio + DualSense + situation chapters, all stamped with `session_id` + `clock_ns` + `frame_seq`. Foundry **cuts** from the Stem. Monitor / Deck **look at** the Stem. The Conductor publishes which program the glasses should show. It does **not** switch scenes.

Full operator doc: [docs/STEM.md](https://github.com/ConWan30/Qoresence/blob/main/docs/STEM.md)

## Flags

| Piece | Flag | Default |
|-------|------|---------|
| Conductor | rides `--play` | On with play (bus only, no disk) |
| Program-out | `--stem-program` | OFF — implies `--monitor` |
| Audio | `--stem-audio` | OFF — capture-card audio pin only |
| Record | `--stem-record` | OFF — `clips/stem_*.mp4` |

No `--stem-stream`. No Twitch. No Virtual Cam. No scene stack.

## Operator

```powershell
python -m qoresence.cli --play --deck --stem-program --streamer-fps 60
```

`/health` exposes `stem.mode`, `stem.audio.age_s`, `stem.record.active`.

## What it is not

- Not a 1.0 gate. Prove capture health, score lock, and one HDMI clip first.
- Not a rebuild of OBS. Platform streams stay a separate app if you still want them.
- Not a laptop mic. Unplugged HDMI stays silent.

## Modes

`watch` → `prime` → `armed` → `hold` → `encode` — same rules as Theater `director.ts`, now on `RetinaEventBus` as `stem_program`.
