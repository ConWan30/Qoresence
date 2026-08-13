# Foundry Bay — Ghost Cut

Foundry Bay is Qoresence Studio. **Ghost Cut** edits a **local HDMI clip + chapter receipt** into a highlight with the why-strip burned in. No LTX key. Default-off, post-session, never on the live event bus.

## Why a fourth glass

Retina Deck already has three live surfaces:

| Glass | URL | Job |
|---|---|---|
| Clutch Lens | `/overlay.html` | In-game HUD. Invisible when boring. |
| Retina Rail | `/deck.html` | Live console. Situation, controller, clip. |
| Ghost Replay | same WS | 3s memory on the rail. |

Studio is a different job. The operator is no longer playing. They are choosing a chapter and pouring it into a reel. That does not belong on the 18% live rail.

**Foundry Bay** (`/studio.html`) is the fourth glass: same Stadium Glass tokens as Deck, dedicated page, no live capture, no WebSocket.

```
Deck (play now)  ──Make HDMI clip──►  clips/*.mp4 + *.chapters.json
                                              │
                                              ▼
                                   Foundry Bay (after the clip)
                                   clip → frame @ t_s → LTX reel
                                   receipt stays local
```

## Operator path

```powershell
# Live session with Studio available (does not render until you ask)
python -m qoresence.cli --play --deck --studio --streamer-device 0 --streamer-fps 30

# Open the bay
# http://127.0.0.1:8765/studio.html

# Or one-shot after the session (Ghost Cut, local, no LTX)
python -m qoresence.cli --foundry-reel --foundry-reel-count 1
```

Key file: `.secrets/ltx.key` (gitignored). A labeled line such as `LTX: ltxv_…` is accepted.

## What the page does

1. **Candidates** — Foundry ranks chaptered clips (confirm / score_changed first).
2. **Splice rail** — CLIP → FRAME → REEL. The causal chain is the whole point.
3. **Render reel** — queues one job. Deck HTTP handler runs the scan off the event loop.
4. **Jobs** — poll every 5s. Completed reels play in-page. Receipt shows job id + prompt.

Keyboard: `R` render selected, `D` back to Deck.

## Hard rules

- Default **OFF**. `--studio`, `--foundry-reel`, or `QORESENCE_STUDIO_ENABLED=1`.
- No bus emits. No lobe locks. Worker thread is not the capture path.
- Frames leave the box only when the operator hits Render. Output MP4 + `.receipt.json` stay local.
- Prompts lock **film-grade 3D graphics** (lighting, motion, finish). Players stay football players matching the source frame — not Avatar faces, not anime-eye redesign. LTX has no negative-prompt field, so the lock is the leading clause of the positive prompt.
- LTX-2.3-pro durations are 6 / 8 / 10 seconds. Qoresence snaps invalid values (including the old 5s default) to 6.
- Signed GCS upload/download send **only** the headers LTX required. No Bearer token on storage URLs.
- Deck `POST /api/foundry/render` ignores client `output_dir` and only resolves clip names under `clips/`.

## API

| Method | Path | Role |
|---|---|---|
| GET | `/studio.html` | Foundry Bay |
| GET | `/api/foundry/status` | enabled / key / model |
| GET | `/api/foundry/candidates` | ranked clips |
| POST | `/api/foundry/render` | queue jobs (`wait=false`) |
| GET | `/api/foundry/jobs` | recent jobs |
| GET | `/media/reels/{name}` | reel MP4 or receipt JSON |
