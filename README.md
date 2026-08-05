# Qoresence

**Observation-plane presence engine for gamers.**  
Synchronizes controller inputs with live video feed (capture card or OBS Virtual Cam) to produce gamer-owned causal presence evidence.

## Purpose

A background engine that:
- Captures UVC video (capture card or OBS Virtual Camera)
- Optionally reads local HID (controller) inputs
- Correlates the two streams causally
- Emits structured, gamer-owned events with shared `session_id` + `clock_ns`
- Never claims humanity, eligibility, or "anti-cheat"

## Non-Negotiable Rules

- **Observation plane only** — no PoAC, no FROZEN commitments, no chain writes
- **All lobes default to `enabled = False`** — operator explicitly enables each
- **Eye-check mandatory** for any video source before trusting frames
- **Every event carries** `session_id` + `clock_ns` (monotonic) + `source_lobe`
- **First-class game profiles**: NCAA Football 27 and Call of Duty (equal citizens)
- **QorTroller independent** — core runs with zero knowledge of QorTroller; optional adapter later

## Quick Start (when implemented)

```bash
# Install
pip install -e .

# Run (all lobes default OFF - enable explicitly)
python scripts/run_qoresence.py --streamer-enabled --streamer-device 0 --controller-enabled
```

## Project Structure

```
Qoresence/
├── qoresence/
│   ├── core/           # Session, Config, EventBus, Types
│   ├── lobes/          # streamer, controller, screen, outcome, visual
│   ├── fusion/         # presence fusion engine
│   ├── outputs/        # JSONL, WebSocket, receipts
│   └── adapters/       # optional QorTroller adapter
├── tools/obs/          # OBS Browser Source overlay
├── scripts/            # CLI entry points
├── tests/              # Unit + integration tests
└── docs/               # Architecture, Roadmap
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Devin Implementation Directive](docs/DEVIN.md)

## License

MIT — see [LICENSE](LICENSE)