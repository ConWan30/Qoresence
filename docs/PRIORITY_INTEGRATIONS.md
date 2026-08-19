# Priority integrations

Sequential interoperable layers on **SessionTimeline** (shared causal clock).

| Phase | Module | Role |
|-------|--------|------|
| **A** | `agents/session_timeline.py` | Drive/session memory; `why_last` |
| **B** | `agents/prediction_lifecycle.py` | arm → open → resolve \| cancel |
| **C** | `vision/clip_chapters.py` + Deck | `.chapters.json` + why strip |

## Flow

```text
FastMoment / MomentScorer execute
        │
        ▼
 SessionTimeline.append  ◄── PredictionLifecycle transitions
        │
        ├── Deck GET /api/timeline + situation.timeline.why_last
        └── Foundry export → chapters_after_export → *.chapters.json
```

## Operator

```powershell
python -m qoresence.cli --play --deck --controller --monitor --streamer-device 0 --streamer-fps 60
```

- Deck **Why it fired** strip updates on fast/confirm moments  
- Fast arm appears as timeline `arm`; TTL (45s) → `prediction_cancel`  
- OCR score → `prediction_resolve` + confirm chat  
- Make Clip writes `clips/*.chapters.json` (chapters + buttons + why)
- With `--otel`: clip export also writes `clips/*.otel.json` (trace IDs + Jaeger URLs) and `clips/*.coupling.json` (per-frame IVC history + InputRing events)  

Optional: `$env:QORESENCE_TIMELINE_PERSIST = "1"` → JSONL under `logs/timeline/`.

## Rules

- Timeline is the **only** long-lived causal log for these features  
- Fast path never invents score digits  
- No second capture; no Twitch-delay clock  
