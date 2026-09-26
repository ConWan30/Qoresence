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

## Segments (chapters sidecar)

When the Noul observatory is on (`--noul`, default OFF), `<name>.chapters.json` gains a `segments` list. It covers Stem Record and Foundry HDMI clips alike, including windowed exports. Each segment describes what was on screen and how much pad↔picture activity there was: `{t0_s, t1_s, hud_kind, presence, confidence, true_pause, label}`. `hud_kind` is one of live_hud / preplay / select_plate / pause / menu / loading / no_board / unknown, and `presence` is idle / join / dense / unknown. `confidence` is hi / mid / lo and `true_pause` is yes / maybe / no / na. Runs shorter than 1.5 s fold into their neighbour and cap its confidence at mid; merges keep the weakest evidence.

- The sidecar also carries `segments_source: "noul"` and `licenses_digits: false`. Labels are closed and descriptive, never "clutch", "highlight", or "best".
- With Noul off, the `segments` key is absent (fail closed).
- The Deck clip player shows a segment strip plus seek buttons, and a "Skip pauses/menus/loading" toggle that is off by default. It never skips `lo`-confidence segments.
- Stem Record's chapter window is its start/stop `clock_ns`.

## Record mux

`--stem-record` (default OFF) runs a `stem-record` thread off the capture and bus threads.

- **Sampling.** The thread samples the ClipBuffer LIVE slot, decodes each new JPEG, and writes `clips/stem_<stamp>_raw.avi` at a fixed 30 fps.
- **Pacing.** Frames are placed by their `clock_ns`, so video time equals session wall time and chapters and segments line up.
- **Gaps.** Short capture gaps repeat the current frame. Gaps longer than 0.5 s are written as **black frames**, so a stall shows as dark, never as a frozen picture.
- **Stop.** On stop, ffmpeg transcodes to browser-safe H.264 `clips/stem_<stamp>.mp4`, and the chapters sidecar is written next to it. Without ffmpeg the raw `.avi` is kept, and its sidecar sits next to it.
- **Excision.** With `--clip-excise` (still default OFF; `--play` and `--stem-record` do not turn it on), stop enqueues a Cut Receipt for that MP4 on the `clip-excise` worker. The original file stays. The first 12 candidate spans are judged; the rest are kept. A raw AVI is not excised. The Theater lists `stem_*.mp4` next to HDMI clips.
- **Health.** `/health` → `stem.record` reports `frames_out`, `dark_frames`, `late`, `dropped`, `fps`, and `h264`.

## Card audio in the record

With both `--stem-audio` and `--stem-record` on (each default OFF), the Stem MP4 carries the capture card's audio.

- **Track.** A `stem-audio-writer` thread writes mono 16-bit `clips/stem_<stamp>.wav` at the card's native sample rate. The PortAudio callback only enqueues blocks (drop-oldest).
- **Alignment.** Samples are placed on the same `clock_ns` as the video, starting at the record's `start_ns`. If audio falls more than 40 ms behind, silence fills the gap; if it runs more than 40 ms ahead, the block head is trimmed. The track is padded to the video length before the mux.
- **Mux.** ffmpeg muxes the WAV as AAC into the H.264 MP4, then deletes the WAV. If the audio mux fails, the MP4 is written video-only and the WAV is kept next to it.
- **Health.** `/health` → `stem.record` reports `audio`, `audio_capturing`, and `audio_track` (blocks, silence_ms, trimmed_ms, dropped_blocks).
- **Privacy.** Raw PCM never goes on the bus; the bus carries only `rms` and `onset`. Laptop mics are never opened. Without a card audio device, the record is video-only.

## Pilot order

1. Capture health, VLM score lock, one local HDMI clip (card in).
2. Conductor + Program-out — this is what makes OBS unused for **ops**.
3. Audio and Record after a real match proves LIVE is healthy.

OBS remains optional only if you still want a platform stream. That is a different product.
