# Qoresence Architecture

## Overview

Qoresence is a local **capture → situation → stream** pipeline. It ingests game
events, screen context, and optionally video/HID, then produces a structured
situation model used by **ClutchBot** for Twitch chat, clips, predictions, and
viewer panels. The trio-retina / fusion layers are kept as optional research
paths but are not part of the ClutchBot MVP.

## Plane Separation

| Plane | Responsibility | Qoresence default |
|-------|----------------|-------------------|
| **Capture** | Video, HID, screen, game events, visual context | Enabled per-lobe by operator |
| **Situation** | Rolling score, state, APM, last outcomes | `SituationModel` |
| **Stream/Social** | Twitch chat, clips, predictions, viewer panel | **ClutchBot** |

**Qoresence (ClutchBot MVP) never:**
- Claims humanity, eligibility, or "anti-cheat"
- Writes to chain
- Stores biometric data centrally

Optional `trio-retina` / `fusion` modules remain for research use but are off by default.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionAuthority                         │
│  mints: session_id, session_head_ns, device_id_hex         │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│   Streamer     │ │  Controller    │ │   Screen       │
│   Lobe         │ │   Lobe         │ │   Lobe         │
│  (UVC/OBS)     │ │   (HID)        │ │  (WGC/DXGI)    │
└───────┬────────┘ └───────┬────────┘ └───────┬────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                  ┌────────────────┐
                  │   Outcome      │
                  │   Lobe         │
                  │ (game profiles)│
                  └───────┬────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌────────────────┐ ┌────────────────┐ ┌────────────────┐
│   Visual       │ │   Fusion       │ │   Outputs      │
│   Lobe (VLM)   │ │   Engine       │ │  (JSONL/WS)    │
└────────────────┘ └────────────────┘ └────────────────┘
```

---

## Lobe Definitions

### Streamer Lobe (`lobes/streamer.py`)
- **Source**: UVC capture card (direct) or OBS Virtual Camera
- **Output**: `activity`, `frame_stats`, `zone` events
- **Eye-check**: Mandatory first frame verification
- **Presence-sync**: `presence_sync_ok` gated on controller touch file

### Controller Lobe (`lobes/controller.py`)
- **Source**: Local HID (DualShock Edge, generic)
- **Output**: Controller events with `causal_parent_ns`
- **Rolling buffer**: For causal correlation

### Screen Lobe (`lobes/screen.py`)
- **Source**: WGC / DXGI / mss screen capture
- **Output**: cv_motion optical flow, OCR HUD regions
- **Correlation**: Binds to controller lobe via `clock_ns`

### Outcome Lobe (`lobes/outcome.py`)
- **Source**: Game-specific event detectors
- **Profiles**: NCAA Football 27, Call of Duty (equal first-class)
- **Events**: Profile-specific (snap, down_advanced, kill, death, etc.)

### Visual Lobe (`lobes/visual.py`)
- **Source**: Sampled frames → VLM (NVIDIA Nemotron or compatible)
- **Output**: `VisualContext` (game-aware), `CrossModalVerdict`
- **Sampling**: Configurable frame sample rate

---

## Fusion Engine (`fusion/presence.py`)

Consumes all lobe events from the `RetinaEventBus` and produces:

```python
@dataclass
class PresenceReport:
    session_id: str
    clock_ns: int
    presence_sync_ok: bool                    # controller-backed optical activity
    weighted_verdict: WeightedVerdict         # fusion of all lobes
    lobe_contributions: dict[str, float]      # per-lobe weights
    anomalies: list[Anomaly]                  # cross-lobe mismatches
```

**Weighted verdict components:**
- Streamer presence-sync (weight: configurable)
- Controller causal density (weight: configurable)
- Screen coupling score (weight: configurable)
- Outcome coherence (weight: configurable)
- Visual confirmation (weight: configurable)

---

## Event Schema

All events emitted to `RetinaEventBus` must carry:

```json
{
  "session_id": "grind_2024_001",
  "clock_ns": 1234567890123456789,
  "session_head_ns": 1234567890000000000,
  "source_lobe": "streamer|controller|screen|outcome|visual",
  "type": "activity|frame_stats|zone|controller_event|outcome_event|visual_context",
  "payload": { ... }
}
```

**Separation Law (Observation Plane):**
- Events NEVER carry: `verdict`, `authored_kills`, `claim`, `asserts`, `presence_score`, `humanity`, `is_human`, `eligible`, `is_eligible`, `eligibility`, `poac`, `kas`, `poac_chain_root`

---

## Outputs

### JSONL (`outputs/jsonl.py`)
- Append-only, one JSON object per line
- Path: `logs/qoresence_<session_id>.jsonl`
- Rotation: daily or size-based

### WebSocket (`outputs/websocket.py`)
- Default: `ws://127.0.0.1:8765`
- Broadcasts all events to connected clients
- Consumers:
  - `tools/obs/presence_overlay.html` (OBS Browser Source)
  - `tools/twitch-extension/panel.html` (Twitch Extension / Browser Source)
  - `ClutchBot` agent

### Receipts (`outputs/receipt.py`) — Optional
- Cryptographic receipts for event batches
- Merkle root over event batch for auditability
- Used by the optional `trio-retina` research path, not the ClutchBot MVP

---

## ClutchBot (`qoresence/agents/`)

ClutchBot is the default consumer of the event bus for the Twitch MVP.

```
┌───────────────┐
│  ClutchBot    │
│  Agent        │
├───────────────┤
│ SituationModel│  rolling game state
│ MomentScorer  │  clutch-moment rules
│ ActionExecutor│  pluggable backends
│ TwitchIRC     │  chat + commands
│ TwitchHelix   │  clips, predictions
│ TwitchEventSub│  follow/sub/redemption alerts
└───────────────┘
```

Agent events are written to the same JSONL and WebSocket, so the OBS overlay
and Twitch panel can display the same data in real time.

---

## Configuration

Single source of truth: `RetinaUnifiedConfig` (see `core/unified_config.py`)

- All lobes default `enabled = False`
- ClutchBot default `enabled = False`
- Never claim humanity / eligibility
- Game profiles: NCAA Football 27, Call of Duty (extensible)

---

## QorTroller Adapter (Optional, Later)

`adapters/qortroller.py` — thin compatibility layer:

- Accepts pre-minted `session_id`, device identity, attested HID window
- Maps QorTroller session → Qoresence session
- **Never** imports QorTroller at module level in core
- **Never** writes PoAC / FROZEN / chain
- **Never** changes default-OFF lobe posture