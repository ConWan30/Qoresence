# Grok bot handoff — 2026-09-12

Operator: Contr. Repo: `ConWan30/Qoresence`, branch **`main` @ `5f6b1a8`**.
This session did **not** dual-open the capture card. Pattern B only.

Read first: `AGENTS.md` (event-bus lock + ticket-clock), `docs/NOVELTY_OBSERVATORY.md`, `docs/SEQGATE.md`, `docs/CAPTURE_OWNERSHIP.md`.

**Do not** print/store stream keys or API keys. **Do not** paint last-good digits. **Do not** enable `--a2a` / `--agent-society` / Streamr / Twitch as product path.

---

## What this session shipped (on `main`)

| PR | What |
|---|---|
| #189 | Madden NFL abbrev gate + hollow-zero VLM (`NO 0` is 0, not all-nulls) |
| #196 | One Quicksilver slot (ClutchFeed / MatchAgent / VLM / Visual) |
| #204 | ClutchFeed harvests snapshot moments; MatchAgent surfaces licensed stub if LLM quiet; score `0` is `0-7` not `?-7` |
| #208 | Browser `GET /api/observations` = Aperture Glass UI; JSON via `Accept: application/json`; `--observations` |
| #209 | Look-graphs reuse HOLD refreshes ConfirmTicket clock |
| #210 | Hub **full-frame** hash ≠ scorebug ticket crop (false `crop_mismatch`) |
| #211 | Overlay digit-gate crop chain (follow-on) |
| #212 | Chat **skips** busy Quicksilver slot; VLM timeout backoff **max 2s**; JPEG q70 |
| #213 | **Every VLM HTTP 200** bumps `ConfirmTicket.clock_ns` on the same ticket_id |

Also earlier in the same long thread (already on `main` before this file): Null Digit / freshness, capture lease + OBS `DUAL_OPEN`, Integrity Board, Coupling Meter, SEQGATE v0, X Glass default-OFF, Pattern B helper `.sentinel` wipe (OBS 32 ignores `--disable-shutdown-check`).

---

## Last known live command (keep these flags)

Capture was **not flowing** at handoff (`USB3.0 Video` missing / CoInitialize on rebind). Replug the card, then:

```powershell
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONPATH = 'C:\Users\Contr\Qoresence;' + $env:PYTHONPATH
$env:QORESENCE_OBSERVATIONS = '1'
Set-Location C:\Users\Contr\Qoresence
& .\.venv\Scripts\python.exe -m qoresence.cli --play --deck --controller --ghost-stick --haptic-probe --match-agent --agent-glass --deck-lease-lamp --look-graphs --learning-edge --observations --streamer-fps 60 --game-profile madden_27 --no-game-detect
```

**Always** `--game-profile madden_27 --no-game-detect` while this operator plays Madden. Auto-detect kept pinning **College Football**.

Kill every `qoresence.cli` python **before** start (one DShow owner). Do not open the card in OBS.

---

## URLs (Sight Glass)

| Surface | URL |
|---|---|
| Theater / observatory overlay | http://127.0.0.1:8765/deck.html |
| Observations glass (Aperture, **this is the obs journal UI**) | http://127.0.0.1:8765/api/observations (browser = HTML; fetch `Accept: application/json` = JSON) |
| Same HTML | http://127.0.0.1:8765/observations.html |
| Lens (OBS Browser Source) | http://127.0.0.1:8765/overlay.html |
| HDMI pixels | http://127.0.0.1:8765/obs-live.html |

Theater SPA on disk: `qoresence/deck/glass_spa/index-uQperNCN.js`. Hard-refresh after SPA rebuilds.

**Not the same HUD:** `/overlay.html` is SEQGATE + Aperture **score pill**. Theater `/deck.html` is the revamped observatory overlay (`ObservatoryHUD`). Observations journal is `/api/observations`.

---

## Flags ON vs OFF (do not “enable everything”)

**ON in the launch above:** play, deck, controller observe, ghost-stick, haptic-probe, match-agent, agent-glass, deck-lease-lamp, look-graphs, learning-edge, observations, 60 fps, Madden pin.

**Stay OFF:** `--a2a`, `--agent-society`, `--x-glass` (needs grant), `--spout-glass`, `--otel`, `--streamr`, Twitch, stem audio/record/program, `--monitor` (OpenCV highgui broken here), `--tray` (no pystray).

QorGraph loops 1/2/4/5 are **code law**, not flags.

---

## Last healthy in-game snapshot (before capture drop)

- `game_profile`: **madden_27**, gameplay, CIN/NO then PHI/NO
- HDMI: `age_s` ~0.02, **60 fps**, `same_seq` true
- After #212 restart: SEQGATE **`licensed`**, speech `3-17`, VLM 3 calls / **0 timeouts**, ticket age ~3.9s
- Later check (pre-#213 process): SEQGATE **`ticket_stale`** again — VLM HTTP 200 returned **12–15 / SELECT** (pause plate), mint skipped, last good **13–31** aged ~137s. That is what #213 is for.
- MatchAgent often `{}` on menu; on licensed gameplay it should show `Board licensed on this seq.` if muse-spark skips the slot
- `/api/observations`: `enabled: true`, **0 records** until a football moment opens on the visual bus

**At handoff:** process waiting for card (`device_index=-1`, `frames=0`, SEQGATE `no_ticket`). Replug USB3.0 Video.

---

## What still needs doing (finish this)

### P0 — capture back, then prove SEQGATE

1. Replug **USB3.0 Video**. Confirm `/health` `state.video.age_s < 1`, `frames`/`pushes` climbing, `target_fps` 60.
2. In **gameplay** (not pause SELECT):  
   `$h = Invoke-RestMethod http://127.0.0.1:8765/health`  
   Expect `situation.game_profile = madden_27`, `seqgate.licensed = true`, `seqgate.speech` like `13-31` not `□–□`, ticket `delta_s` **< 8**.
3. If still `ticket_stale` **after HTTP 200**, log `scoreboard_vlm.last` vs `confirm.last_confirm.clock_ns` vs `video.clock_ns`. #213 should bump clock on 200 even when parse is junk.

### P0 — VLM still flaky

- Visual VLM still **holds the Quicksilver slot ~14s**. Chat already skips (`acquire 0.05s`). Next: Visual POST should **skip** like chat (`acquire_quicksilver(0.05)`), not wait 14s, or SEQGATE will starve again.
- `skip_inflight_count` was 159 in one sample. Confirm interval vs inflight watchdog.
- Pause/SELECT crops return 12–15 with no wordmarks — tighten Madden crop / refuse ungrounded 200s for **remint**, but still refresh clock (#213).

### P1 — ClutchFeed / MatchAgent

- Muse-spark skips while VLM owns the slot → template heartbeats + MatchAgent stub. Fine for SEQGATE. If operator wants LLM lines, serialize **after** confirm 200, don’t steal the slot.
- `license_score_text` turns mismatched pairs into `Score update: board.` — only keep digits that match the ticket.

### P1 — Observations journal empty

- Runtime is ON; `records: []` until Astra football adapter opens a moment. Prove one candidate on `/api/observations` during a Madden play, then claim-ledger jump-to-evidence.

### P1 — X Live (deferred; operator stopped go-live)

- Pattern B: Qoresence owns the card; OBS Browser Sources only (`/obs-live.html` + `/overlay.html`).
- **`main` obs-live is 30 fps MJPEG cover (#163).** Laptop freeze session proved JPEG `/live.jpg` @ 60 + QSV 720p60 ultra-low. Do not dual-open DShow.
- OBS 32.2 **ignores** `--disable-shutdown-check`. Helper must wipe `%APPDATA%\obs-studio\.sentinel` (already in `tools/obs/pattern_b_x_live.ps1`).
- PowerShell **`$args` is reserved** — helper uses `$obsArgs`.
- Live Studio TIMED OUT if OBS sat on Safe Mode. Ethernet > Wi-Fi AX210 (`10054`).
- Stream key pasted in an old chat is **burned** — rotate; never echo.

### P2 — product chrome

- Astra **uncertainty channels** have **no Theater TS** bindings. Observatory HUD is `ObservatoryHUD` on `/deck.html`; not cloned onto Lens.
- ROADMAP still lists lease / Integrity Board / Coupling Meter unchecked — they **are** on `main` (01592e3 era). Update the checklist.
- Ident Latch (#145) remains HOLD. SEQGATE is not that.

---

## Verify commands

```powershell
# health
$h = Invoke-RestMethod http://127.0.0.1:8765/health
$h.state.situation | Select-Object game_profile,game_title,home_team,away_team,score_vlm_locked,home_score,away_score
$h.state.seqgate
$h.state.scoreboard_vlm | Select-Object calls,timeout_count,inflight,last_http_status
$h.state.video | Select-Object age_s,target_fps,same_seq,clock_ns

# observations JSON
Invoke-RestMethod http://127.0.0.1:8765/api/observations -Headers @{Accept='application/json'}
```

Tests that lock this slice:  
`tests/test_confirm_ticket.py` (refresh clock), `tests/test_vlm_timeout_inflight.py`, `tests/test_overlay_digit_gate.py`, `tests/test_seqgate.py`, `tests/test_observations_page.py`, `tests/test_capture_lease.py`, `tests/test_deadlock_regression.py`.

---

## File map (touch these, don’t invent lobes)

- SEQGATE: `qoresence/sync/seqgate.py`, `qoresence/sync/digit_integrity.py`, `qoresence/deck/seeing_health.py`
- Confirm: `qoresence/vision/confirm_ticket.py` (`refresh_licensed_ticket_clock`)
- VLM: `qoresence/vision/scoreboard_vlm.py`, `qoresence/agents/quicksilver_slot.py`, `qoresence/agents/llm_client.py`
- Extractor mint: `qoresence/vision/scoreboard_extractor.py`
- Lens: `qoresence/deck/overlay.html`
- Observations UI: `qoresence/deck/observations.html`, `qoresence/deck/server.py` (`GET /api/observations`)
- Theater overlay: `glass/src/components/theater/observatory-hud.tsx`, `hdmi-stage.tsx` `variant="observatory"` — rebuild SPA → copy `glass/dist` → `qoresence/deck/glass_spa/`
- Pattern B: `tools/obs/pattern_b_x_live.ps1`

Event-bus: never emit while holding a lobe lock (`tests/test_deadlock_regression.py`).
