# Pilot verification after C1–C4 harden

Local only. No second capture. No Quicksilver from the monitor.

## Run

```powershell
cd C:\Users\Contr\Qoresence
# Terminal A — one owner of USB3.0 Video idx 0
python -m qoresence.cli --play --deck --monitor --controller --streamer-device 0 --streamer-fps 60 --game-profile madden_27
# or ncaa_football_27

# Terminal B — does not open DShow
python -m qoresence.cli --pilot-closeout
# or the existing pilot monitor that writes logs/pilot/session_*.jsonl
```

If you already have a `logs/pilot/session_*.jsonl`:

```powershell
python -c "from pathlib import Path; from qoresence.pilot.closeout import write_closeout; p=sorted(Path('logs/pilot').glob('session_*.jsonl'))[-1]; print(write_closeout(p)[:2])"
```

## Confirm the closeout JSON (no full JSONL needed)

Open `logs/pilot/closeout_*.json` and check:

| Question | Field |
|---|---|
| Did locks hold? | `score_lock_timeline` + `score_lock_true_ratio` |
| Real score plays? | `climax_chapters` — `touchdown` / `field_goal` should outrank `board` |
| Why FREEZE? | `freeze_classified[].kind` ∈ card_stall / graph_stall / deck_lock / unknown |

Markdown must contain headings: `## Score lock timeline`, `## Climax chapters`, `## FREEZE classified`.

## Spot-checks

- A confirmed TD chapter has `climax_score` ≥ 0.9 and `source` = `confirm`.
- t0 Live-board dumps are lower or marked `stale_after_rollback` after a score drop.
- Madden: `nameplate_ambiguous` on situation / closeout `nameplate_ambiguous_n` when HUD said a last name with no unique roster hit.

## Metric note

`DECK_DOWN` samples are also tagged `FREEZE` / `deck_lock`. Do not compare raw `freeze_events` 1:1 with closeouts from before C3.
