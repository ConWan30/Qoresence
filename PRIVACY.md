# Privacy & Data Policy

Qoresence is **local-first** by design.

## What stays on your machine

- HDMI video frames from the capture card.
- Clip ring and exported `clips/*.mp4` files.
- Controller input events and `logs/`.
- Situation model, coupling scores, and event bus history.

None of these leave the machine unless you explicitly enable a glass that sends them out.

## What can leave your machine (opt-in)

| Feature | Data sent | How to enable |
|---------|-----------|---------------|
| Leftover Twitch IRC | Chat messages | leftover `--clutchbot-channel` + token (not the local route) |
| Leftover Twitch Helix clips | Clip URL to chat | leftover `--clutchbot-enable-clips` + `clips:edit` (prefer local Foundry MP4) |
| Quicksilver VLM | Scoreboard crop + metadata. **With a Quicksilver key set, images are uploaded** (see below). | `QORESENCE_QUICKSILVER_*` |
| A2A bus | Scene description + prompt | `--a2a` |
| Streamr | Selected events | `qoresence/streamr/`, experimental and default OFF |
| Trio / IoTeX block RPC | A JSON-RPC `eth_blockNumber` request (no frames, no game data) to `https://babel-api.testnet.iotex.io` by default; your IP is visible to that host | `--trio`; the URL can be changed with `--trio-block-rpc` / `QORESENCE_TRIO_BLOCK_RPC` and the call needs the optional `aiohttp` package |
| MediaPipe model download | A one-time download of `efficientdet_lite0_uint8.tflite` from `storage.googleapis.com` into `./models/`; nothing of yours is sent except the normal request metadata (your IP) | **Off by default.** Only if you set `QORESENCE_ALLOW_MODEL_DOWNLOAD=1`, `mediapipe` is installed (`game` extra) and `models/efficientdet_lite0.tflite` is not already present. See "Model download" below |

## Cloud uploads when a Quicksilver key is set

Local-only is the default. If a Quicksilver API key is found, image data **is** sent to `api.quicksilverpro.io`. A key counts if it comes from `QORESENCE_QUICKSILVER_API_KEY`, `QUICKSILVER_API_KEY`, `QORESENCE_SCOREBOARD_VLM_API_KEY`, **or a key file** such as `.secrets/quicksilver*.key` in the directory you launch from. A leftover key file is enough to turn it on.

With a key present:

- **Scoreboard crops** (a JPEG crop of the scoreboard, base64-encoded, plus a prompt) are uploaded: `qoresence/vision/scoreboard_vlm.py` (`requests.post`, with a `urllib` fallback).
- **Whole frames, resized to at most 640 px wide as JPEG,** are uploaded by the visual lobe: `qoresence/lobes/visual.py` (two `session.post` call sites). Without a key the visual lobe uses the local heuristic instead.
- **Text prompts** (no images) go to the same service for ClutchBot (`qoresence/agents/llm_client.py`, `--clutchbot`), the agent society (`qoresence/agents/society/quicksilver.py`, `--agent-society`) and A2A (`qoresence/a2a/gemini_agent.py`, `--a2a`).

Without a key, none of the above runs and no outbound connection is made by the default `--deck`, `--play` or `--stream` paths.

## Model download

`qoresence/vision/motion_tracker.py` (`_ensure_mediapipe_model`) can fetch the EfficientDet-Lite0 model from `https://storage.googleapis.com/mediapipe-tasks/object_detector/efficientdet_lite0_uint8.tflite` into `./models/efficientdet_lite0.tflite`. **It never downloads unless you opt in with `QORESENCE_ALLOW_MODEL_DOWNLOAD=1`** (exactly `1`). It is reached from two places, and both need the `mediapipe` package:

1. **Motion tracking** (`MotionTracker`, used by the vision stack). The game-detection vision stack only enables it when a cloud key is set. Without the model and without opt-in, the MediaPipe foreground mask is simply disabled (a warning is logged).
2. **The capture person-check** in `qoresence/lobes/streamer.py` (`_frame_contains_person`). It runs when a local (non-network) capture device opens, `QORESENCE_PRIVACY_GUARD` is not `0`, the device name is not a recognised physical capture card, and `eye_check_required` is on (the default). **It fails closed:** if the model is missing and you have not opted in (or `mediapipe` is not installed, or anything else goes wrong), the device is treated as not cleared and capture is refused, with a log line explaining how to fix it. Recognised physical capture cards skip this check and are unaffected.

To enable the person-check on a non-allowlisted device (for example an OBS virtual camera), either set `QORESENCE_ALLOW_MODEL_DOWNLOAD=1` for a one-time download (the cached file is used afterwards), or place the model file at `models/efficientdet_lite0.tflite` yourself (relative to the directory you launch from) and no download is made. Other libraries you install (for example `easyocr`, `paddleocr`, `ultralytics`) may fetch their own weights on first use; that is their behavior, not Qoresence code.

## Browser requests to third parties

None of the bundled Deck pages load fonts or scripts from a third party: Instrument Sans and IBM Plex Mono are served from your own machine. (Earlier versions of `civif.html` requested Google Fonts, which would have shared the viewer's IP address with Google; that was removed.)

## What we do **not** do

- Continuous 60 fps upload to the cloud. (This is a statement about rate, not about whether images are sent: see "Cloud uploads when a Quicksilver key is set" above.)
- Store biometrics or controller fingerprints.
- Make humanity, legitimacy, or anti-cheat claims.
- Train models on your data unless you explicitly export `clips/` for that purpose.

## Best practices

- Keep `.secrets/` gitignored and never share token files.
- Delete `clips/` and `logs/` between sessions if you do not want local residue.
- Use `127.0.0.1` for Deck/AgentGlass on shared machines; enable token auth if you tunnel.

## Questions

Open a Discussion or email through the security contact in `SECURITY.md`.
