# Pilot Session Checklist — Phase 7 Validation

**Goal:** Validate all Phase 7 features (evidence chains, router predicates, tool loop, learned router, audit CLI, Deck evidence panel) against a real game.

---

## Pre-Session Setup

- [ ] Kill any stale Qoresence processes (port 8765)
- [ ] Verify capture card is connected: `python -m qoresence.cli --streamer-list`
- [ ] Verify API keys exist: `.secrets/quicksilver_clutchbot.key` and `.secrets/quicksilver_vlm.key`
- [ ] Set environment variables:
  - `QORESENCE_A2A=1` (enable A2A orchestrator)
  - `QORESENCE_A2A_GEMINI=1` (live Gemini scene agent)
  - `QORESENCE_A2A_DEEPSEEK=1` (live DeepSeek chat agent)
  - `QORESENCE_LATENCY_LOG=1` (enable latency logging)
- [ ] Clear old logs: `del logs\events.jsonl` (start fresh)
- [ ] Record commit hash: `git rev-parse --short HEAD`

## Launch Command

```
qoresence.bat
```
or
```
python -m qoresence.cli --play --a2a --game-profile ncaa_football_27
```

For OpenTelemetry causal tracing / clip sidecars (optional):
```
python -m qoresence.cli --play --deck --controller --monitor --otel --streamer-device 0 --streamer-fps 60
docker compose --profile otel up -d
```

---

## During Session — Watch For

### OpenTelemetry / clip sidecars (optional — `main` now)
- [ ] Did clip export write `.otel.json` and `.coupling.json` sidecars? Check `clips/`.
- [ ] Does `.coupling.json` contain `coupling_history` with `frame_seq` / `video_clock_ns`?
- [ ] Does `.coupling.json` `input_ring_events` match the buttons actually pressed in that clip?
- [ ] Is `otel.reentrant_cycles_total` in `/health` staying low/flat? (spikes mean a lobe is re-entering on the same thread)
- [ ] Is `otel.dropped` staying at 0 (exporter queue is not backing up)?

### A2A Commentary Quality
- [ ] Does A2A fire on touchdowns, field goals, red zone entry, 4th down, 2PC, OT start?
- [ ] Does A2A **suppress** on menu screens (except menu_exit)?
- [ ] Are scene descriptions specific (not generic "stadium hums")?
- [ ] Does DeepSeek rewrite add energy without inventing scores?
- [ ] Any team name hallucinations? (should be fixed, but verify)
- [ ] Near-duplicate veto working? (check /health for veto count)

### Evidence Chains (NEW — Phase 7.1)
- [ ] Open Deck in browser: `http://127.0.0.1:8765/deck.html`
- [ ] Click "evidence" link — does the evidence panel load?
- [ ] Do evidence chains appear after A2A commentary?
- [ ] Each chain should show: reason, confidence, drive phase, coupling, cited events, cited fields
- [ ] Confidence color-coding: green (>0.7), yellow (0.4-0.7), red (<0.4)

### Router Decisions (NEW — Phase 7.2)
- [ ] In the evidence panel, do router decisions appear?
- [ ] Do you see both "fire" and "suppress" decisions? (not just fires)
- [ ] Do must-fire predicates show up? (big_play, red_zone_entry, fourth_down, etc.)
- [ ] Check: does 4th down trigger a fire? (new predicate)
- [ ] Check: does 2PC attempt trigger a fire? (new predicate)

### Tool Loop (NEW — Phase 7.3)
- [ ] Check /health — does it show `tools` in the A2A stats?
- [ ] If agents are live, do they reference recent events in their output?
  (e.g., "after that touchdown" or "following the field goal")
- [ ] Check JSONL log for any tool-call activity

### Audit CLI (NEW)
- [ ] After session (or mid-session from another terminal), run:
  ```
  python -m qoresence.cli --audit 10
  ```
- [ ] Does it print evidence chains with cited events and fields?
- [ ] Does it print router decisions with fire/suppress counts?

---

## Post-Session

- [ ] Run audit: `python -m qoresence.cli --audit 20`
- [ ] Check JSONL log for `evidence_chain` events: `findstr "evidence_chain" logs\events.jsonl | measure`
- [ ] Check JSONL log for `router_decision` events: `findstr "router_decision" logs\events.jsonl | measure`
- [ ] Fill in pilot notes (copy this template to `logs/pilot/pilot_notes_YYYYMMDD.md`)

## Pilot Notes Template

```
| Field | Value |
|-------|--------|
| **Date** | YYYY-MM-DD |
| **Game / mode** | |
| **Pattern** | B (Qoresence owns card) |
| **Build / commit** | |
| **Session length** | |

## Evidence chains
- Did they appear in Deck? Y/N
- Were cited events correct? Y/N
- Were cited fields correct? Y/N
- Confidence calibration: too high / too low / about right?

## Router decisions
- Did fire/suppress decisions appear? Y/N
- Must-fire predicates firing correctly? Y/N
- 4th down predicate: fired? Y/N
- 2PC predicate: fired? Y/N
- OT predicate: fired? Y/N

## Tool loop
- Did agents reference recent events? Y/N
- Any tool-call errors in log? Y/N

## Audit CLI
- `--audit N` worked? Y/N
- Output readable? Y/N

## Top 3 issues
1.
2.
3.
```
