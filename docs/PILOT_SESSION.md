# CFB pilot session runbook

Safe, repeatable operator checklist. Architecture is on `main`; this is how you **fly** it.

---

## Pre-session

1. **Pick capture pattern** — [CAPTURE_OWNERSHIP.md](CAPTURE_OWNERSHIP.md)  
   - **B** (recommended): Qoresence owns physical card  
   - **A**: OBS owns card → Virtual Cam  

2. **OBS conflict check**  
   - Pattern B: no Video Capture Device on `USB3.0 Video`  
   - Pattern A: Start Virtual Camera before Qoresence  

3. **Preflight**

   ```powershell
   python scripts/pilot_preflight.py
   python -m qoresence.cli --streamer-list
   ```

4. **Start stack**

   ```powershell
   # Pattern B
   python -m qoresence.cli --play --deck --monitor --streamer-fps 60
   # optional A2A window later: add --a2a (and Quicksilver key under .secrets/)
   ```

5. **Verify live**

   ```powershell
   (Invoke-RestMethod http://127.0.0.1:8765/health).state.video.has_frame
   # expect True within ~10s
   ```

   Deck: http://127.0.0.1:8765/deck.html (hard-refresh if tab was stale)

---

## During session (~game)

| Watch | Expect |
|-------|--------|
| **Score lock** | Situation strip / health shows plausible home-away (VLM referee) |
| **Clutch feed** | Sparse chat (not identical spam); score moments on real flips |
| **Timeline** | `GET /api/timeline` — events accumulate |
| **Foundry** | Deck **Make HDMI Clip** or API → `clips/hdmi_clip_*.mp4` (+ optional chapters) |
| **Monitor** | Retina Monitor window = FrameHub (not Twitch delay) |

Optional **10–15 min A2A** window:

```powershell
# restart or start with:
python -m qoresence.cli --play --deck --monitor --streamer-fps 60 --a2a
```

Note qualitative feel only (no Truth-plane claims).

---

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
