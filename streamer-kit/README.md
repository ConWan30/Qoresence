# Qoresence Streamer Kit (beta)

Free setup bundle for Madden streamers who use OBS. It wires the Qoresence
[OBS bridge](../docs/OBS_BRIDGE.md) into a ready-made OBS scene. The optional signed
[truth feed](../docs/TRUTH_FEED.md) is documented but not turned on by this kit.
Full guide: [docs/STREAMER_KIT.md](../docs/STREAMER_KIT.md).

## What is in the box

| File | What it is |
|---|---|
| `Qoresence_Streamer_Kit.scene.json` | OBS scene collection: scene **`Qoresence Score`** holding a Text (GDI+) source **`Qoresence Score Text`** (gold text, aqua outline, navy plate). |
| `qoresence-stream.cmd` | Windows launcher template. It reads the obs-websocket password from `QORESENCE_OBS_PASSWORD` or a secret file and starts Qoresence with `--obs --obs-text-source "Qoresence Score Text"`. |
| `README.md` | This file. |

**Why the text source is not named `Qoresence Score`.** The bridge's default text
source is `Qoresence Score`, but OBS scenes and sources share one name namespace, so a
scene and a source cannot both use that name (OBS error 601). The launcher passes
`--obs-text-source "Qoresence Score Text"` to match.

## Requirements

Windows, OBS Studio 28+ (obs-websocket v5 built in, port 4455), an HDMI capture card
owned by Qoresence (do **not** add it as a Video Capture Device in OBS), Madden 27, and
a Qoresence checkout installed with `pip install -e ".[obs]"`.

## Setup

1. OBS → **Tools → WebSocket Server Settings**: enable the server, keep port 4455, enable auth, copy the password from **Show Connect Info**.
2. OBS → **Scene Collection → Import** → pick `Qoresence_Streamer_Kit.scene.json`, then switch to it. Add your usual game/display capture to the `Qoresence Score` scene underneath the text.
3. OBS → **Settings → Output → Replay Buffer**: enable it (20–30 s), then **Start Replay Buffer** before you play.
4. Save the password: `setx QORESENCE_OBS_PASSWORD "<password>"` (new terminal afterwards), **or** write it on one line in `%USERPROFILE%\.qoresence\obs_password.txt`.
5. Copy `qoresence-stream.cmd` next to `qoresence.bat` in your Qoresence folder and double-click it. Extra flags are forwarded (e.g. `--obs-scene "Qoresence Flash" --obs-scene-hold 4`, `--obs-chapters`, `--obs-no-replay`, `--truth-feed`).

## Beta honesty

- The text shows a score **only** when Qoresence has locked it and capture is live; otherwise it is blank. Unsure reads trigger nothing.
- Only a locked score **increase** saves a replay / switches scene.
- A capture-freeze fix is pending a live test. If the overlay stays blank, check `http://127.0.0.1:8765/health` → `obs_bridge`.
- The scene JSON import has been schema-checked in CI, not yet import-tested on every OBS version.

Build the zip locally: `python scripts/build_streamer_kit.py` → `dist/qoresence-streamer-kit.zip`.
