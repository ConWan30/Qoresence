# Qoresence

**Local game-state capture and Twitch ClutchBot MVP for streamers.**

Qoresence ingests live game events and screen context, builds a structured,
real-time situation model, and drives **ClutchBot** — a Twitch chat companion
that narrates clutch moments, auto-creates clips, runs predictions, responds to
chat commands, and shows a viewer panel.

---

## Purpose

Qoresence is an opt-in, local-only observation layer for game streams. It does
not claim humanity, act as anti-cheat, or write to chain. Its default output is
a local JSONL event log and a WebSocket feed for overlays and the Twitch
Extension panel.

| What It Does | What It Doesn't Do |
|--------------|-------------------|
| Observes game events and screen/HID context | ❌ Claim humanity / eligibility |
| Produces a structured game-state event stream | ❌ Act as anti-cheat |
| Runs ClutchBot for chat, clips, predictions | ❌ Write to chain |
| Exports JSONL / WebSocket for overlays | ❌ Store biometric data centrally |

### Why this matters

For streamers, game-aware chat bots currently require manual triggers or deep
per-game integrations. Qoresence closes that gap by deriving state directly
from the capture feed and game events, then acting on Twitch. Everything runs
locally and the streamer decides which features are enabled.

---

## Architecture: Capture → Situation → ClutchBot

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         QORESENCE CAPTURE PLANE                             │
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────┤
│  STREAMER    │  CONTROLLER  │    SCREEN    │   OUTCOME    │    VISUAL    │
│  (UVC/OBS)   │  (HID API)   │  (mss/DXGI)  │  (Game API)  │   (VLM)      │
│              │              │              │              │              │
│  Frame stats │  Trigger/HID │  CV motion   │  Game events │  Visual ctx  │
│  Zone detect │  Tremor samp │  OCR HUD     │  Score/state │  Cross-modal │
└──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘
       │             │             │             │             │
       └─────────────┴─────────────┴─────────────┴─────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   RETINA EVENT BUS      │
                    │  (JSONL + WebSocket)    │
                    └───────────┬─────────────┘
                                │
                    ┌───────────┼───────────┐
                    ▼           ▼           ▼
          ┌──────────────┐ ┌──────────┐ ┌──────────────┐
          │  CLUTCHBOT   │ │   OBS    │ │ OPTIONAL     │
          │  (Twitch     │ │ Browser  │ │  trio-retina │
          │   agent)     │ │  Source  │ │  / fusion    │
          └──────────────┘ └──────────┘ └──────────────┘
```

---

## Components

### Core (`qoresence/core/`)
| Module | Purpose |
|--------|---------|
| `session.py` | `SessionAuthority`, `SessionIdentity` — session identity and event ordering |
| `event_bus.py` | `RetinaEventBus` — central event router (JSONL + WebSocket outputs) |
| `unified_config.py` | `RetinaUnifiedConfig` — capture lobe + ClutchBot + optional trio-retina config |
| `types.py` | `SourceLobe`, `EventType`, `BaseEvent` — shared type system |

### Lobes (`qoresence/lobes/`)
| Lobe | Status | Input | Output Events |
|------|--------|-------|---------------|
| **Streamer** | ✅ | UVC capture card / OBS Virtual Cam | `frame_stats`, `zone`, `activity` |
| **Controller** | ✅ | DualShock Edge HID | `trigger_onset`, `stick_motion`, `tremor_sample` |
| **Screen** | ✅ | mss / DXGI capture | `cv_motion`, `ocr_hud`, `coupling_score` |
| **Outcome** | ✅ | Game memory / API (NCAA 27, CoD) | `outcome_event` |
| **Visual** | ✅ | VLM (ONNX / API) | `visual_context`, `cross_modal_verdict` |

**All lobes default `enabled = False`** — operator explicitly enables each.

### Fusion (`qoresence/fusion/`)
| Component | Purpose |
|-----------|---------|
| `PresenceFusionEngine` | Cross-modal coupling, presence reports |
| `FusionWeights` | Tunable weights per modality |

### Trio-Retina Validation (`qoresence/trio/`) — **Optional Layer**
| Module | Purpose |
|--------|---------|
| `config.py` | `TrioRetinaConfig` — ingest/flush modes, on-chain flags |
| `payload.py` | `EvmLogPayload` builder matching w3bstream applet format |
| `wasm.py` | `WasmtimeRunner` — CLI subprocess + embedded wasmtime |
| `validator.py` | `TrioRetinaValidator` — async batch validation |
| `metrics.py` | Prometheus exporter for validation stats |

**Validation modes**:
- `validate_on_ingest` — per-event (high latency, not recommended)
- `validate_on_flush` — batch every N seconds (default 30s, recommended)

**On-chain gates** (DEPIN-1 LEG 2):
- `node_session_verify` — `node_id` + `session_root` spine
- `retina_events_root_verify` — events Merkle root
- `pq_commitment_source=real` — ZKSepProof Groth16 (requires artifacts)

### Tools
| Tool | Purpose |
|------|---------|
| `tools/obs/presence_overlay.html` | OBS Browser Source — real-time telemetry dashboard |
| `tools/twitch-extension/panel.html` | Twitch Extension / Browser Source viewer panel |
| `scripts/quickstart.sh\|.bat` | New developer onboarding (<5 min) |

### Agents (`qoresence/agents/`)

**ClutchBot** — game-state-aware Twitch companion for Qoresence.

| Feature | Status | Trigger | Output |
|---------|--------|---------|--------|
| Chat narration | ✅ | Clutch moments (score, turnover, red zone) | `agent_action` + Twitch PRIVMSG |
| Auto-clips | ✅ | High-weight clutch moments | Twitch clip + edit URL in chat |
| Predictions | ✅ | Red-zone close-game drives | Twitch channel-point prediction |
| Chat commands | ✅ | `!state`, `!score`, `!lastclip`, `!help` | PRIVMSG replies |
| Follow / sub / redemption alerts | ✅ | EventSub WebSocket | Thank-you PRIVMSG |
| Viewer panel | ✅ | Browser Source / Extension | `tools/twitch-extension/panel.html` |

See [docs/clutchbot_setup.md](docs/clutchbot_setup.md) for Twitch app, tokens, and scopes.

---

## Quickstart

```bash
# 1. Clone & setup
git clone https://github.com/ConWan30/Qoresence.git
cd Qoresence
./scripts/quickstart.sh       # Linux/macOS
# or
scripts\quickstart.bat        # Windows

# 2. Dry-run the stream preset
python -m qoresence.cli --dry-run --stream \
  --clutchbot-channel mychannel

# 3. Stream with ClutchBot (see docs/clutchbot_setup.md for tokens)
qoresence --stream \
  --clutchbot-channel mychannel \
  --clutchbot-username clutchbot_qoresence \
  --clutchbot-token-file /path/to/bot_oauth.txt \
  --clutchbot-client-id <client_id> \
  --clutchbot-broadcaster-username mychannel \
  --clutchbot-enable-clips \
  --clutchbot-enable-predictions

# 3. Manual lobe selection (same as --stream)
qoresence --outcome --visual --clutchbot \
  --clutchbot-channel mychannel ...

# 4. Optional trio-retina validation (advanced)
qoresence --streamer --controller --outcome --screen --visual \
  --trio --trio-wasm-path=w3bstream_applet.wasm
```

### Docker (Real WASM + ZKSepProof)

```bash
# Build (includes wasmtime, Node.js, snarkjs, ZKSepProof artifacts)
docker build -t qoresence:latest .

# Run with trio-retina
docker run --rm qoresence:latest --dry-run --trio \
  --trio-wasm-path=/app/w3bstream_applet.wasm \
  --trio-validate-on-flush

# Production via Compose
docker-compose up -d
# Configure via .env (see docker-compose.yml)
```

---

## Configuration

### Environment Variables (Production)

```bash
# Core trio-retina
export QORESENCE_TRIO_ENABLED=1
export QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm
export QORESENCE_TRIO_VALIDATE_ON_FLUSH=1
export QORESENCE_TRIO_FLUSH_INTERVAL=30.0

# On-chain path (requires w3bstream project)
export QORESENCE_TRIO_BLOCK_RPC=https://babel-api.testnet.iotex.io
export QORESENCE_TRIO_NODE_SESSION_VERIFY=1
export QORESENCE_TRIO_EVENTS_ROOT_VERIFY=1

# PQ Commitment
export QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=real
export VAPI_ZK_ARTIFACTS_DIR=/app/zk_artifacts

# Device Identity (DualShock Edge VMDR)
export QORESENCE_DEVICE_ID_HEX=<64-hex VMDR pubkey hash>
```

### CLI Flags (Override Env)

```bash
qoresence --trio \
  --trio-wasm-path=/app/w3bstream_applet.wasm \
  --trio-validate-on-flush \
  --trio-flush-interval=30 \
  --trio-block-rpc=https://babel-api.testnet.iotex.io \
  --trio-node-session-verify \
  --trio-events-root-verify \
  --trio-pq-commitment-source=real
```

---

## Monitoring

### Health Endpoint
```bash
curl http://localhost:8765/health | jq .trio_retina
```

### Prometheus Metrics (`/metrics`)
| Type | Metrics |
|------|---------|
| **Counter** | `qoresence_trio_retina_validations_total{result="success\|failure"}` |
| **Histogram** | `validation_duration_seconds`, `payload_size_bytes` |
| **Gauge** | `flush_interval_seconds`, `last_flush_timestamp`, `pending_events`, `wasm_runner_status`, `enabled`, `node_session_verify`, `events_root_verify` |
| **Info** | `pq_commitment_source` |

### Integration
```python
from qoresence.trio import TrioRetinaMetricsMiddleware, instrument_validator

# ASGI middleware
app.add_middleware(TrioRetinaMetricsMiddleware, path="/metrics")

# Auto-instrument validator
instrument_validator(validator)
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [trio-retina Integration](docs/trio-retina-integration.md) | Architecture, data flows, validation modes |
| [trio-retina Runbook](docs/trio-retina-runbook.md) | Operator procedures, deployment, troubleshooting |
| [ClutchBot Setup](docs/clutchbot_setup.md) | Twitch app, tokens, scopes, and panel setup |
| [Architecture](docs/ARCHITECTURE.md) | Core observation plane design |
| [Roadmap](docs/ROADMAP.md) | Planned phases |

---

## Testing

```bash
# All tests
python -m pytest tests/ -v

# ClutchBot agent specific
python -m pytest tests/test_clutchbot.py -v

# Trio-retina specific
python -m pytest tests/test_trio_retina.py -v

# Benchmarks
python scripts/benchmark.py
cat benchmark_results.json
```

**Current status**: 200+ tests passing.

---

## Performance Benchmarks (Local)

| Component | Throughput | Latency (p50/p95/p99) |
|-----------|------------|----------------------|
| EventBus.emit_raw | **15,948 events/sec** | 0.06 / 0.12 / 0.25 ms |
| build_evm_log_payload (100 events) | **373 ops/sec** | 2.7 / 3.1 / 4.2 ms |
| JSON serialize/deserialize | ~6,000 ops/sec | <0.5 ms |
| WASM validation (mocked) | **34,907 ops/sec** | 0.02 / 0.05 / 0.30 ms |
| WASM validation (real, wasmtime) | **3.1 ops/sec** | **148 / 593 / 593 ms** |
| mock_pq_commitment | **1.1M ops/sec** | ~0.001 ms |
| Memory (100 payloads × 10 events) | 118 ops/sec | ~29 MB peak |

---

## Project Structure

```
Qoresence/
├── .github/workflows/ci.yml          # GitHub Actions CI
├── docs/
│   ├── trio-retina-integration.md    # Integration design
│   ├── trio-retina-runbook.md        # Operator procedures
│   ├── clutchbot_setup.md            # Twitch app, tokens, scopes
│   ├── ARCHITECTURE.md               # Core architecture
│   └── ROADMAP.md                    # Roadmap
├── qoresence/
│   ├── core/                         # Session, EventBus, Config, Types
│   ├── lobes/                        # streamer, controller, screen, outcome, visual
│   ├── agents/                       # ClutchBot Twitch agent
│   │   ├── clutchbot.py
│   │   ├── helix_client.py
│   │   ├── twitch_client.py
│   │   ├── eventsub_client.py
│   │   └── moment_scorer.py
│   ├── fusion/                       # PresenceFusionEngine, FusionWeights
│   ├── trio/                         # trio-retina validation layer
│   │   ├── config.py
│   │   ├── payload.py
│   │   ├── wasm.py
│   │   ├── validator.py
│   │   └── metrics.py                # Prometheus exporter
│   └── cli.py                        # Main CLI entry
├── tools/obs/presence_overlay.html   # OBS Browser Source overlay
├── tools/twitch-extension/panel.html # Twitch Extension / Browser Source panel
├── scripts/
│   ├── quickstart.sh                 # Linux/macOS onboarding
│   ├── quickstart.bat                # Windows onboarding
│   └── benchmark.py                  # Performance benchmarks
├── tests/
│   ├── test_trio_retina.py           # 31 trio-retina tests
│   └── ... (153 core tests)
├── Dockerfile                        # Multi-stage with wasmtime + snarkjs
├── docker-compose.yml                # Production compose
├── pyproject.toml                    # Dependencies + [trio] extra
└── README.md
```

---

## Dependencies

### Core
- Python ≥3.11
- `pydantic≥2.0`, `numpy≥1.24`

### Optional Extras (`pip install -e ".[extra]"`)
| Extra | Dependencies | Purpose |
|-------|--------------|---------|
| `streamer` | `opencv-python`, `websockets` | Video capture |
| `controller` | `hidapi` | DualShock Edge HID |
| `screen` | `mss`, `opencv-python` | Screen capture |
| `visual` | `requests`, `onnxruntime` | VLM inference |
| `twitch` | `requests`, `websockets` | ClutchBot Twitch agent |
| **`trio`** | `trio-retina≥0.3.0`, `wasmtime≥16.0`, `prometheus-client≥0.19` | **trio-retina validation** |
| `dev` | `pytest`, `ruff`, `mypy` | Development |

---

## Background: V.A.P.I. and trio-retina

Qoresence originally grew out of the V.A.P.I. (Verifiable Autonomous Physical
Intelligence) research direction. The capture plane, session identity, and
optional `trio-retina` validation layer are kept for that longer-term work, but
they are **not part of the ClutchBot MVP**. The default product is a local
game-state capture + Twitch agent stack. Validation, on-chain anchoring, and
cryptographic presence proofs remain opt-in experiments.

---

## License

MIT — see [LICENSE](LICENSE)

---

## Related Projects

| Project | Relationship |
|---------|--------------|
| **vapi-pebble-prototype** | Source of trio-retina w3bstream applet, ZKSepProof circuits, DualShock Edge calibration (research) |
| **QorTroller** | V.A.P.I. protocol — Qoresence shares the observation-plane concept |
| **MachineFi / trio-retina** | w3bstream applet mechanical validation standard (research) |

---

*Generated with [Devin](https://devin.ai)*