# OBS bridge (spike) — locked score → OBS

**Status:** opt-in spike. Default **OFF**. Live-verified against OBS 32.2.2 (obs-websocket 5.7.4) on Windows.

The OBS bridge lets Qoresence drive OBS Studio from its **locked** scorebug reads.
It talks to OBS through **obs-websocket v5** (built into OBS 28+). It never opens the
capture card and never draws pixels into OBS itself.

## What it does

When a **locked** score changes (`score_vlm_locked` = ConfirmTicket minted), the bridge:

1. **Saves the replay buffer** (`SaveReplayBuffer`). Saves are rate-limited (at most one per 20 s by default).
2. Optionally **flashes a scene** (e.g. `Qoresence Flash`) for N seconds and then switches back to the scene you were on. If you switch scenes yourself during the hold, it does not switch back.
3. **Sets a text source** (default `Qoresence Score`) to the locked score, e.g. `KC 14 - 7 BUF`.
4. Optionally adds a **record chapter marker** (`CreateRecordChapter`, OBS 30.2+, Hybrid MP4 only). If OBS refuses the request, the bridge ignores it.

### Honesty rules (fail-closed)

- The text source shows a score **only** while the score is locked **and** the capture is live (FrameHub has a frame younger than 5 s). If there's no lock, a blank or partial read, no frame, or a stale frame, the text is set to **empty**. The bridge never shows a guessed score.
- Only a locked score **increase** fires the replay, scene and chapter actions. The first lock of a session sets the baseline and only updates the text. A locked decrease (new game or correction) also only updates the text. Re-locking the same score after an unlock does nothing beyond showing the text again.
- Unlocks and blank reads never trigger replays.

### Safety

- **Separate process, network protocol only.** Qoresence talks to OBS over a local WebSocket using the MIT-licensed `obsws-python` client. Nothing links against OBS or loads into it as a plugin, so there is no GPL plugin linkage.
- **No second capture of the card.** The bridge only sends obs-websocket requests. Qoresence still owns the HDMI card ([OBS_OWNS_CARD.md](OBS_OWNS_CARD.md)). Never add a Video Capture Device in OBS for the same physical card.
  - Note: OBS's replay buffer records **what OBS is outputting**. In the recommended layout, that's Display/Game/Window capture plus the Lens browser source, not the card itself. Qoresence's own HDMI clips are separate.
- **Never blocks Qoresence.** The bus subscriber only enqueues (AGENTS.md rules 1/4/5). All OBS I/O runs on a separate `obs-bridge` daemon thread. If OBS is closed or unreachable, the bridge logs **one** WARNING and retries in the background with backoff (1 s → 30 s). Qoresence keeps running.
- **Password stays private.** It's read from `QORESENCE_OBS_PASSWORD` only, never from a CLI flag. It never appears in logs, `/health` or error strings. `obsws-python`'s own logger prints the password on connect, so the bridge silences that logger.

## OBS setup (one time)

1. **Tools → WebSocket Server Settings**: check **Enable WebSocket server**. Keep port **4455**, enable authentication, and click **Show Connect Info** to copy the password.
2. **Settings → Output → Replay Buffer**: check **Enable Replay Buffer** and set a max replay time (e.g. 20–30 s). Click **Start Replay Buffer** in the Controls dock before you play. `SaveReplayBuffer` fails if the buffer isn't running. The bridge records that as `last_error` and keeps going.
3. Create a **Text (GDI+)** source named **`Qoresence Score`**. Style it with the deck look: aqua glow on a near-black navy plate, and **gold** text, because it only ever shows locked scores.
4. *(Optional)* Create a scene named **`Qoresence Flash`** to flash on score changes, e.g. a full-screen version of the scorebug text or the Lens browser source.
   OBS scenes and sources share **one** name namespace: a scene and the text source can't both be called `Qoresence Score` (OBS refuses with code 601). If your scene is already `Qoresence Score`, name the text source something else and pass `--obs-text-source`.
5. *(Optional, OBS 30.2+)* For chapter markers, set the recording format to **Hybrid MP4** and start recording.

## Install & launch (Windows laptop)

```powershell
cd C:\Users\Contr\Qoresence
.\.venv\Scripts\Activate.ps1          # or your existing env
pip install -e ".[obs]"

$env:QORESENCE_OBS_PASSWORD = "<from OBS Show Connect Info>"
# optional: $env:QORESENCE_OBS_HOST = "localhost"; $env:QORESENCE_OBS_PORT = "4455"

.\qoresence.bat --play --deck --monitor --tray --a2a --controller --streamer-fps 60 --obs --obs-scene "Qoresence Flash" --obs-scene-hold 4
```

That's the `qoresence.bat` default line with `--obs` added. `qoresence.bat` forwards its arguments to `python -m qoresence.cli`. Leave out `--obs-scene` if you don't want scene flashes.

| Flag / env | Default | Meaning |
|---|---|---|
| `--obs` / `QORESENCE_OBS=1` | off | enable the bridge |
| `QORESENCE_OBS_HOST` | `localhost` | obs-websocket host |
| `QORESENCE_OBS_PORT` | `4455` | obs-websocket port |
| `QORESENCE_OBS_PASSWORD` | empty | password (**env only**) |
| `--obs-text-source` / `QORESENCE_OBS_TEXT_SOURCE` | `Qoresence Score` | text input to set |
| `--obs-scene` / `QORESENCE_OBS_SCENE` | none | scene to flash on change |
| `--obs-scene-hold` / `QORESENCE_OBS_SCENE_HOLD_S` | `4` | seconds before switching back |
| `--obs-chapters` / `QORESENCE_OBS_CHAPTERS=1` | off | add record chapter markers |
| `--obs-no-replay` / `QORESENCE_OBS_REPLAY=0` | replay on | skip `SaveReplayBuffer` |
| `QORESENCE_OBS_REPLAY_MIN_INTERVAL_S` | `20` | replay save rate limit |

## Health

When the bridge is enabled, `GET http://127.0.0.1:8765/health` includes an `obs_bridge` block. When it's off, the block is missing.

```json
"obs_bridge": {
  "enabled": true, "connected": true,
  "last_action": "text", "last_action_age_s": 3.2,
  "actions": 7, "actions_by_kind": {"text": 3, "replay": 1, "scene": 1, "scene_restore": 1, "text_blank": 1},
  "last_error": "", "events_seen": 812, "showing_score": true,
  "config": {"host": "localhost", "port": 4455, "password_set": true, "text_source": "Qoresence Score", "...": "..."}
}
```

## Code

- `qoresence/obs/bridge.py`: config, obs-websocket adapter (lazy `obsws_python` import), and the bridge worker.
- Wiring: `QoresenceApp.__init__` in `qoresence/cli.py` subscribes the bridge to `RetinaEventBus` `visual_context` events. `/health` is in `qoresence/deck/server.py`.
- Tests: `tests/test_obs_bridge.py` uses a fake OBS client, with no network and no OBS needed.
