# Football product bar (CFB 27 + Madden 27)

One title. Observation plane only. This match, these hands, this clip.

| Bar | Rule |
|---|---|
| Subject | Gemini/OCR crop stops at `y=0.93`. Ticker / crawl is other games. |
| Lock | Confirm ticket licenses score digits. Stranger identity (Oregon/Wisconsin crawl) cannot replace the locked pair. |
| Huddle | Locked board + down/quarter is **gameplay**, even if the VLM says menu. |
| Hands | Phrases `SNAP`/`SPRINT`/`CUT`/`RELEASE` mint a coupling ticket. Heat-speech needs that ticket. |
| Society | Auditor reads confirm ticket + phrase. Coach cites phrase. |
| Foundry | `*.chapters.json` why-strip: confirm ticket · couple ticket · phrase. |

Madden: start with `--game-profile madden_27`. Identity uses the NFL club catalog (KC/PHI), not NCAA schools. NCAA `apply_identity` is skipped on Madden so a Chiefs bug cannot become a college cardinal.

```powershell
python -m qoresence.cli --play --deck --monitor --controller --a2a --streamer-device 0 --streamer-fps 60 --game-profile madden_27
```

Restart `--play` to load. Live check: lock stays on the two teams in the big scorebug; a sprint shows `phrase=SPRINT` and a `coupling_ticket_id`.
