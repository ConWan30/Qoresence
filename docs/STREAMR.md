# Streamr Network Integration

Qoresence can publish live game events, game state, and A2A reasoning to the
[Streamr Network](https://streamr.network) through a local Streamr node. This
gives you encrypted, scalable, one-to-many distribution of your session data.

## How it works

1. You run a local **Streamr node** with the HTTP, MQTT, or WebSocket plugin
   enabled.
2. You create a stream on Streamr (e.g. `0x.../qoresence/football`) and grant
   the node permission to publish to it.
3. Qoresence's `StreamrPublisher` connects to the local node and POSTs/PUBLISHes
   JSON events as they happen on the `RetinaEventBus`.
4. The node signs and forwards the data into the Streamr Network, where
   subscribers anywhere in the world can consume it.

## Quick start

### 1. Install and run a Streamr node

```bash
npm i -g @streamr/node
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

The node's API key is in `~/.streamr/config/default.json` under
`apiAuthentication.keys`.

### 2. Create a stream and grant permissions

```bash
npm install -g @streamr/cli-tools
# or use the SDK in a small script
```

You need a small amount of `POL` on Polygon mainnet (or use Polygon Amoy
testnet). Create a stream and grant the node address `PUBLISH` and `SUBSCRIBE`
permissions.

### 3. Start Qoresence with Streamr publishing

```powershell
.\qoresence.bat --streamr `
  --streamr-stream-id "0xYOUR_ADDRESS/qoresence/football" `
  --streamr-protocol http `
  --streamr-host 127.0.0.1 `
  --streamr-port 7171 `
  --streamr-api-key "YOUR_NODE_API_KEY" `
  --streamr-event-types "*"
```

You can also enable specific event types:

```powershell
--streamr-event-types "presence_report,visual_context,outcome_event"
```

### 4. Verify

Subscribe to the stream from another terminal:

```bash
streamr stream subscribe 0xYOUR_ADDRESS/qoresence/football
```

You should see Qoresence events flowing in real time.

## Configuration options

All options are also available in `qoresence/core/unified_config.py` as
`StreamrConfig` and on the CLI.

| CLI flag                  | Default           | Meaning                                      |
|---------------------------|-------------------|----------------------------------------------|
| `--streamr`               | off               | Enable Streamr publishing                    |
| `--streamr-stream-id`     | `""`              | Streamr stream ID                            |
| `--streamr-protocol`      | `http`            | `http`, `mqtt`, or `websocket`               |
| `--streamr-host`          | `127.0.0.1`       | Local Streamr node host                      |
| `--streamr-port`          | `7171`            | Plugin port                                  |
| `--streamr-api-key`       | `None`            | Node API key (HTTP auth header)              |
| `--streamr-event-types`   | `""`              | Comma-separated types, or `*` for all        |
| `--streamr-max-eps`       | `0`               | Max events per second (0 = unlimited)        |

## Notes

- Publishing is **best-effort and non-blocking**. If the node is down,
  Qoresence keeps running and the streamer is not blocked.
- Raw video is **not** published by default (too large for the event bus).
  Event metadata, game state, and A2A reasoning are published.
- Video distribution can be added later on top of Streamr's WebRTC / StreamrTV
  layer once that SDK is available in Python or via a Node.js bridge.
- The publisher runs in a background thread, so it never stalls the main
  capture loop.
