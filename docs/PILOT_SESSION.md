# CFB pilot session runbook

Safe, repeatable operator checklist. Architecture is on `main`; this is how you **fly** it.

---

## Pre-session

1. **Pick capture pattern** — [CAPTURE_OWNERSHIP.md](CAPTURE_OWNERSHIP.md)  
   - **B** (recommended): Qoresence owns physical card  
   - **A**: OBS owns card → Virtual Cam  

2. **OBS conflict check (Pattern B hard rule)**  
   - **Pattern B:** OBS must **not** have a `Video Capture Device` source pointing at `USB3.0 Video`.  
   - **Why:** One physical DirectShow device has one owner. Dual-open causes black frames, frame drops, or a hung capture card that looks like Qoresence is frozen.  
   - **Pattern A:** Start OBS Virtual Camera *before* launching Qoresence.  

3. **Preflight**

   ```powershell
   python scripts/pilot_preflight.py
   python -m qoresence.cli --streamer-list
   ```

4. **Start stack**

   ```powershell
   # Pattern B — native 720p, 60 fps
   python -m qoresence.cli --play --deck --monitor --streamer-fps 60

   # If the card flutters / age_s climbs with 720p, fall back to native card resolution
   python -m qoresence.cli --play --deck --monitor --streamer-fps 30 --streamer-width 640 --streamer-height 480

   # Or via env (e.g. in a .bat or launcher)
   $env:QORESENCE_STREAMER_WIDTH = "640"
   $env:QORESENCE_STREAMER_HEIGHT = "480"
   ```

5. **Verify live** (in a **second** PowerShell window — leave `--play` running in the first)

   ```powershell
   $h = Invoke-RestMethod http://127.0.0.1:8765/health
   Write-Host "has_frame=$($h.state.video.has_frame)  fps=$($h.state.video.target_fps)"
   # expect has_frame=True within ~10s
   Start-Process http://127.0.0.1:8765/deck.html
   ```

   Deck does **not** open automatically from the CLI. Use the URL above (hard-refresh if the tab was stale).

---

## During session (~game)

### Capture health (read `/health` every few minutes)

```powershell
$h = Invoke-RestMethod http://127.0.0.1:8765/health
$h.state.video
```

Healthy capture values:

| Field | Healthy | Sick | What it means |
|-------|---------|------|---------------|
| `has_frame` | `true` | `false` | Streamer has delivered at least one frame. |
| `age_s` | `< 1.0` | `> 3.0` | Time since the most recent live frame. High `age_s` with `has_frame=true` usually means a software deadlock, not a dead capture card. |
| `frames` | > 0, stable or climbing | stuck at 0 | Ring-buffer population. Capped at `capacity`; if it stops climbing while `pushes` climbs, the buffer is full but not draining. |
| `pushes` | climbing | stuck | Total JPEG pushes to Deck/FrameHub. Should move every few seconds. |
| `skipped` | low | climbing fast | Frames dropped by the clip buffer because they are too old. |
| `fps` | close to `--streamer-fps` | near 0 | Observed capture framerate. |
| `width` x `height` | matches your `--streamer-width/height` | `0x0` | Current capture resolution. |

**If `age_s` climbs while `frames` is stuck and the process is alive**, do not blame the card. Use `py-spy` or attach a debugger; the cause is almost always a lock-ordering / event-cascade deadlock (see `AGENTS.md`).

**If 720p flakes on this card**, drop to the documented 640×480 path above and re-verify `age_s < 1.0` for 10 minutes.

### Situation / score lock (VLM referee)

| Watch | Expect | Pass |
|-------|--------|------|
| **Pause plate, 20–0 blowout** | Deck/situation shows correct home-away, quarter, time if present | Score strip stable for > 5 s after transition. |
| **Score transition** | `state.situation.home_score` / `away_score` flip cleanly, no flicker | No `null` or `0–0` flashes between real scores. |
| **Partial / dirty frame** | VLM holds previous good lock rather than wiping with bad parse | Board may be unreadable for a frame, but `situation` does not regress. |
| **End of game / menus** | `game_state` moves to `menu` or `postgame`, not stuck on `gameplay` | Situation degrades gracefully, not hard-resets. |

If score lock is unreliable, check `logs/events.jsonl` for `visual_context` events and compare against `outcome_event` / OCR. VLM lock should override OCR only when VLM confidence is high and parse is non-null.

### Clutch feed

Sparse chat (not identical spam); score moments on real flips.

### Timeline

`GET /api/timeline` — events accumulate.

### Foundry

Deck **Make HDMI Clip** or API → `clips/hdmi_clip_*.mp4` (+ optional chapters).

### Monitor

Retina Monitor window = FrameHub (not Twitch delay).

Optional **10–15 min A2A** window:

```powershell
# restart or start with:
python -m qoresence.cli --play --deck --monitor --streamer-fps 60 --a2a
```

Note qualitative feel only (no Truth-plane claims).

## Post-session

1. Stop CLI (Ctrl+C)  
2. Optional snapshot:

   ```powershell
   python scripts/pilot_snapshot.py
   # → logs/pilot/pilot_*.json
   ```

3. Fill [pilot_notes_template.md](pilot_notes_template.md) (copy to `logs/pilot/` or your notes store)  
4. Top 3 bugs → GitHub issue or Discussions  

---

## Related

- [RELEASE_HARDENING.md](RELEASE_HARDENING.md)  
- [A2A_CLUTCHBOT.md](A2A_CLUTCHBOT.md)  
- [TWO_SPEED_CLUTCHBOT.md](TWO_SPEED_CLUTCHBOT.md)  
