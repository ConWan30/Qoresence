# Streamr (experimental)

Streamr is an **experimental** research plugin. It is **not** part of the core Qoresence pilot.

## Status

- Default OFF.
- Only consider after local capture, score lock, and local HDMI clips are proven.
- It publishes redacted events to a local Streamr node, not directly to the public chain.

## What it adds

| Qoresence core | Streamr adds |
|----------------|--------------|
| Local capture + scoring | Off-box event distribution |
| Local ClutchBot (Deck + HDMI clips) | A second audience on a DePIN bus |
| Simple setup | Requires a local `streamr-node` and stream grants |

## Quick start

1. Install a local Streamr node:
   ```bash
   npm install -g @streamr/node
   streamr-node
   ```

2. Create a stream and grant the node permission.

3. Start Qoresence:
   ```powershell
   python -m qoresence.cli `
     --play --deck `
     --streamr `
     --streamr-stream-id "0xYOUR_ADDRESS/qoresence/football" `
     --streamr-host 127.0.0.1 --streamr-port 7171
   ```

## Rules

- Never publish raw HID, frames, or A2A prompts.
- Never make the stream publicly subscribable by default.
- Confirm `video.age_s` stays below 1.0s; if it rises, disable Streamr.

See [docs/STREAMR.md](https://github.com/ConWan30/Qoresence/blob/main/docs/STREAMR.md) for full setup.
