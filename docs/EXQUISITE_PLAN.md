# Exquisite Plan — Qoresence Play Mode
> 2026-08-06 21:23 — "Exquisite while playing"

**Goal:** Invisible when boring, exquisite when clutch. You play NCAA 27. Qoresence senses, reasons, and surfaces only what matters — no terminal, no alt-tab, no spam.

## 1. Play Mode — One Command

```bash
python -m qoresence.cli --play
# alias for:
# --game-profile ncaa_football_27 --streamer --streamer-device 0 --streamer-backend dshow
# --visual --visual-prefer-local --visual-sample-rate 6 --fusion --clutchbot
# --clutchbot-llm quicksilver/deepseek-v4-flash @ https://api.quicksilverpro.io/v1
# eye-check mandatory, logs/ + .secrets/ + models/ gitignored
```

- Auto fallback: if `USB3.0 Video not opened` → `OBS Virtual Camera idx2` (logged).
- `cap.grab() retry + fps_target 15` (c953d04) — no `temporal_desync 5.0s`.
- Privacy shutter: `eye_check_<ns>.png` 2s preview (local only, never pushed), then hides.

## 2. What Exquisite Feels Like

| Moment | You See | Qoresence Does |
|---|---|---|
| Boot | 2s `FIELD verified 1.84MB green 0.39` shutter | Streamer DSHOW 1280x720@30 + Visual 6fps warmup |
| Drive | Nothing — game full bleed | MomentScorer silent (`3-6 msg/min` respects `_rate_limit_ok`) |
| 3rd & 2 | **Clutch Lens** fades in 0.8s: `14-7 Q3 3rd&2 00:42 WP 58%→71%` | `FootballScoreboardExtractor` (6a45b58) + `win_probability` + `ClipWorthiness 0.82` |
| Convert | Pulse `CHAINS ⚡` + ClutchBot `Huge 3rd down!` | `Quicksilver deepseek-v4-flash 2.6s` grounded on `situation.to_dict()`, template fallback |
| Quiet | Lens fades, ribbon stays (8% opacity) | `5-frame hysteresis 3/5` (992318e) + `shooter→unknown` (5112e31) — no flicker |

No chrome when not clutch. That's the polish.

## 3. Stack — Already Proven (`6fe965a` `ruff check . 0`)

- **Sense:** USB3.0 Video idx0 DSHOW + allowlist `USB3.0 Video` only + MediaPipe `person BLOCK` + eye-check
- **Train:** `local:heuristic` 5112e31 → hysteresis 992318e → MobileNet-V2 ONNX ee834e1 (`p50 1.12ms` on CLEAN `1.0` precision)
- **Operate:** Scoreboard OCR 383L → SituationModel → MomentScorer/win_prob → ClutchBot → Quicksilver Pro
- **Audit:** `trio-retina` batch 30s `EvmLogPayload {payload_hash/events_root merkle}` → `babel-api.testnet.iotex.io` — `eval 14038 1.0`

## 4. Next: Retina Deck

See `docs/RETINA_DECK_UIUX.md` — OBS Browser Source + Twitch Extension + local Tauri deck. One brain, three glasses.

> **Positioning:** Trio for Entertainment Operations — 10M devices thesis proven on HDMI→Twitch at 1.0 precision, local, private, auditable.
