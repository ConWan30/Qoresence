# Streamr Network Integration (EXPERIMENTAL / OPTIONAL)

**Status:** Research plugin. Not part of the Qoresence MVP or local ClutchBot path.  
**Default:** OFF.  
**Use case:** Only consider this once local capture, score lock, and local HDMI clips are proven.

Qoresence is a **local-first, gamer-facing ops console**. Its job is to lock scores and make local HDMI clips for Deck / Foundry. Streamr does none of that. It is just an extra distribution pipe. Running it leaks session metadata off-box, requires an Ethereum stack, and can confuse the product story.

Do **not** enable Streamr while you are still validating the local pilot.

## Why this is behind a flag

| Qoresence core | Streamr adds |
|----------------|--------------|
| Local capture + VLM scoring | Off-box telemetry distribution |
| Local ClutchBot (Deck + HDMI clips) | A second audience on a DePIN bus |
| Simple gamer setup | Node 20, `streamr-node`, private keys, stream grants |
| Privacy-first session logs | Potentially public on-chain event stream |

## If you still want to experiment

### 1. Install and run a local Streamr node

```bash
npm install -g @streamr/node
streamr-node-init
# enable the http plugin (or mqtt / websocket)
streamr-node
```

Default plugin ports:

| Protocol   | Default port |
|------------|--------------|
| HTTP       | 7171         |
| MQTT       | 1883         |
| WebSocket  | 7170         |

The node API key is in `%USERPROFILE%\.streamr\config\default.json` under `apiAuthentication.keys`.

### 2. Create a stream and grant your node permission

```powershell
$env:USE_STREAMR_MAINNET="0"   # use Polygon Amoy testnet by default
node scripts/create_streamr_stream.js "0xYOUR_PRIVATE_KEY" "0xYOUR_BROKER_NODE_ADDRESS" "qoresence/football"
```

**Do not make the stream publicly subscribable.** Public subscribe can leak scores, game state, and timing. The helper script refuses public subscribe unless you set `I_KNOW_THIS_LEAKS_DATA=1`.

### 3. Start Qoresence with Streamr publishing

```powershell
python -m qoresence.cli `
  --streamr `
  --streamr-stream-id "0xYOUR_ADDRESS/qoresence/football" `
  --streamr-protocol http `
  --streamr-host 127.0.0.1 `
  --streamr-port 7171 `
  --streamr-api-key "YOUR_NODE_API_KEY" `
  --streamr-event-types "presence_report,visual_context,outcome_event"
```

Avoid `--streamr-event-types "*"`. Publish only redacted game-state events, never HID, frames, or raw A2A prompts.

### 4. Verify

```bash
streamr stream subscribe "0xYOUR_ADDRESS/qoresence/football" --private-key YOUR_PRIVATE_KEY
```

### 5. Confirm local health is unchanged

```powershell
curl http://127.0.0.1:8765/health
```

`video.age_s` must stay below 1.0s. If Streamr publishing lags the bus, disable it and move on.

## When this might graduate from experimental

Only after the CFB pilot is boring:

- Publish **redacted** events only (`{game, home, away, quarter}`).
- No public subscribe by default.
- Docs clearly say it is not required for ClutchBot.
- Separate from any anti-cheat / Truth-plane narrative.

Until then, treat it as a sandbox feature and keep it out of the main story.
