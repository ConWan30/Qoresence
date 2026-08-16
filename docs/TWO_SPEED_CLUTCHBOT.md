# Two-Speed ClutchBot

**Novel realtime path:** ClutchBot acts on **video + controller** first; **OCR confirms** facts. OCR is the **referee**, not the starting gun.

Observation-plane only. Controller default **OFF**. Without pad, IVC energy ≈ 0 → fast path stays quiet; confirm path unchanged.

---

## Novelty

| Rule | Meaning |
|------|---------|
| `path=fast` vs `path=confirm` | Every early action is tagged |
| OCR is referee | Soft chat / clip intent / arm_prediction without fresh crops |
| Fast chat never invents score digits | No fabricated `12-7` strings |
| Same clock | `clock_ns` + optional `frame_seq` from FrameHub |
| Graceful degrade | No controller → coupling 0 → fast quiet |

---

## Architecture

```text
Streamer ──► FrameHub (seq, clock_ns) ──► IVC ──► coupling_score (path:fast)
DualSense ─► InputRing ──────────────────┘
                    │
                    ▼
            FastMomentEngine.score_fast(situation, coupling)
                    │  soft chat · clip intent · arm_prediction
                    ▼
              ActionExecutor / Deck / Foundry

Outcome + Visual (OCR/VLM) ──► MomentScorer.score(...)
                    │  path:confirm · factual:true
                    ▼
              factual chat with real scores · resolve prediction
```

| Speed | Source | May invent scores? | Examples |
|-------|--------|--------------------|----------|
| **fast** | IVC coupling + last-known red zone / close / late | **No** | “Red-zone energy spike…” |
| **confirm** | Gemini scoreboard VLM + OCR | Yes, **only digits licensed by a confirm ticket** | “Score update: 21-14” |

A **confirm ticket** is minted when Gemini force-locks the board (`QORESENCE-CONFIRM-TICKET-v0`). Nemotron, Society, and confirm-chat must cite `ticket_id` or score pairs become `board`. Deck `/api/situation` exposes `confirm.last_fast` vs `confirm.last_confirm` (mismatch theater). Ghost Cut why-strip prints the ticket.

A **coupling ticket** (`QORESENCE-COUPLING-TICKET-v0`) is minted when IVC classifies a live play-phrase (`SNAP`/`SPRINT`/`CUT`/`RELEASE`). Heat-speech (“controller heat”, “pad and picture”) is stripped or vetoed without one. Confirm tickets license **digits**; coupling tickets license **pad heat**.

---

## Modules

| Module | Role |
|--------|------|
| `qoresence/sync/input_ring.py` | HID edges |
| `qoresence/sync/frame_hub.py` | Shim → monitor FrameHub |
| `qoresence/sync/ivc.py` | 10–20 Hz join; `path:"fast"` on coupling |
| `qoresence/agents/fast_moment.py` | `FastMomentEngine` |
| `qoresence/agents/moment_scorer.py` | Confirm referee; tags `path=confirm` |
| `qoresence/agents/clutchbot.py` | Fast then confirm dispatch |

---

## Operator use

```text
# Confirm-only (prior behavior; no DualSense)
python -m qoresence.cli --play --deck --streamer-device 0 --streamer-fps 60

# Two-speed: realtime pad heat + OCR confirm
python -m qoresence.cli --play --deck --controller --monitor --streamer-device 0 --streamer-fps 60
```

Fast path **improves** with controller; without it, stack is confirm-only (no crash).

Deck moments may show `[fast]` / `[confirm]` in reason and `path` on payload.

---

## Acceptance

1. Simulated InputRing + red-zone situation → soft chat/clip **without** new OCR event  
2. Soft chat has **no** score digit patterns  
3. OCR `score_changed` still produces confirm chat  
4. No `--controller` → no crash; confirm path only  
5. Single capture owner; FrameHub publish best-effort  

---

## Related

- [CONTROLLER_VIDEO_SYNC.md](CONTROLLER_VIDEO_SYNC.md)  
- [RETINA_MONITOR.md](RETINA_MONITOR.md)  
- [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md)  
- [clutchbot_setup.md](clutchbot_setup.md)  
