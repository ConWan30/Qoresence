# Qoresence × trio-retina Integration Design

## Overview

Integrate MachineFi's **trio-retina** (w3bstream applet + Python bridge) into Qoresence as an **optional validation layer** that provides:

1. **Mechanical PoAC validation** — WASM applet validates payload structure, cadence, PQ proof, retina commitment, node/session spine
2. **On-chain anchoring path** — Validated payloads can be submitted to IoTeX L1 via w3bstream project
3. **PV-CI invariant compliance** — Qoresence events satisfy trio-retina's frozen protocol invariants

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Qoresence Observation Plane                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  Streamer │ Controller │ Screen │ Outcome │ Visual │ Fusion (Presence)     │
│     ↓           ↓          ↓        ↓          ↓           ↓               │
│     └─────────┬───────────┴────────┴──────────┴───────────┘                │
│               ▼                                                             │
│      RetinaEventBus (JSONL + WebSocket)                                     │
│               │                                                             │
│               ▼                                                             │
│      ┌────────────────────────┐                                             │
│      │  TrioRetinaValidator   │  ← NEW: optional validation layer           │
│      │  (wasmtime/subprocess) │                                             │
│      │  • EvmLogPayload gen   │                                             │
│      │  • WASM applet call    │                                             │
│      │  • Exit code handling  │                                             │
│      │  • Logging/audit       │                                             │
│      └───────────┬────────────┘                                             │
│                  │                                                           │
│         ┌───────┴───────┐                                                    │
│         ▼               ▼                                                    │
│   Validation OK    Validation FAIL                                           │
│         │               │                                                    │
│         ▼               ▼                                                    │
│   Continue flow   Emit anomaly /                                             │
│                   Halt on enforce                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │  w3bstream Project  │  (IoTeX MachineFi)
                    │  (console.w3bstream.│
                    │   com registration) │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    IoTeX L1         │
                    │  (PoAC settlement)  │
                    └─────────────────────┘
```

---

## Integration Points

### 1. EvmLogPayload Generation (Qoresence → trio-retina)

**Source**: Qoresence session events + lobe data
**Target**: `EvmLogPayload` struct matching w3bstream applet

```python
# Qoresence side: build from session identity + lobe events
EvmLogPayload = {
    "device_id": session.device_id_hex,           # 64-hex from SessionAuthority
    "block_number": latest_block_number,          # From IoTeX RPC (or mock for local)
    "payload_hash": sha256(session_head + events),# Commitment to session events
    "signature": ed25519_sign(payload_hash),      # Device key (Edge VMDR)
    "pq_commitment": "64-hex",                    # Post-quantum (ML-DSA-65) placeholder
    "retina_state_commitment": "64-hex",          # Visual oracle state root
    "retina_w3bstream_enforce": bool,             # Config flag
    "events_root": "64-hex",                      # Merkle root of event batch
    "retina_events_root_verify": bool,            # Config flag
    "node_id": "64-hex",                          # SHA-256(QORTROLLER-NODE-v0 || device_id || first_session)
    "session_root": "64-hex",                     # Scorecard/PoSP root (optional)
    "node_session_verify": bool,                  # Config flag
}
```

### 2. WASM Applet Invocation

**Method**: `wasmtime` CLI (preferred) or Python `wasmtime` package
**Entrypoint**: `handle_poac_payload(ptr: *const u8, size: usize) -> i32`

| Exit Code | Meaning | Qoresence Action |
|-----------|---------|------------------|
| 0 | OK | Continue |
| 1 | Bad pointer | Log error, anomaly |
| 2 | UTF-8 decode | Log error, anomaly |
| 3 | JSON parse | Log error, anomaly |
| 4 | Block cadence | Log error, anomaly |
| 5 | PQ proof fail | Log error, anomaly |
| 6 | Retina commitment | Log error, anomaly |
| 7 | Events root | Log error, anomaly |
| 8 | Node/session gate | Log error, anomaly |

### 3. Configuration (RetinaUnifiedConfig extension)

```python
@dataclass
class TrioRetinaConfig:
    enabled: bool = False
    wasm_path: str = "w3bstream/applet/target/wasm32-unknown-unknown/release/w3bstream_applet.wasm"
    wasmtime_path: str = "wasmtime"  # or full path
    validate_on_ingest: bool = False  # Enforce at ingestion
    validate_on_flush: bool = True    # Validate batched events periodically
    flush_interval_s: float = 30.0
    block_rpc_url: str = "https://babel-api.testnet.iotex.io"  # For block_number
    pq_commitment_source: str = "mock"  # "mock" | "real" (future)
    node_session_verify: bool = False
```

---

## Implementation Plan

### Phase A: Core Wrapper (Week 1)
1. Add `trio-retina` optional dependency to `pyproject.toml`
2. Create `qoresence/trio/` module:
   - `payload.py` — `EvmLogPayload` builder from Qoresence events
   - `wasm.py` — `WasmtimeRunner` wrapper (subprocess + JSON stdin/stdout)
   - `validator.py` — `TrioRetinaValidator` orchestrator
3. Extend `RetinaUnifiedConfig` with `TrioRetinaConfig`

### Phase B: Event Bus Integration (Week 1-2)
1. Add `TrioRetinaValidator` to `RetinaEventBus` as optional post-write hook
2. Add validation to `PresenceFusionEngine` for presence reports
3. Config flags: `validate_on_ingest`, `validate_on_flush`

### Phase C: Docker/Deployment (Week 2)
1. Update `Dockerfile` with `wasmtime` installation
2. Update `docker-compose.yml` with trio-retina service
3. Copy WASM artifact to image

### Phase D: Tests (Week 2)
1. Unit tests for payload builder
2. Integration test with mock WASM (exit code 0)
3. Failure injection tests (exit codes 1-8)
4. End-to-end with real w3bstream applet

---

## Data Flow Detail

### Event Batch → EvmLogPayload

```python
# Every N events or flush_interval_s
async def build_and_validate(batch: list[Event]) -> ValidationResult:
    # 1. Get session identity
    session = SessionAuthority.current()
    
    # 2. Compute commitments
    payload_hash = sha256(session.session_head_ns.to_bytes(8, 'big') + 
                          json.dumps([e.to_dict() for e in batch], sort_keys=True).encode())
    events_root = merkle_root([e.event_id for e in batch])
    
    # 3. Get block number (RPC call or cached)
    block_number = await get_latest_block_number()
    
    # 4. Build payload
    payload = EvmLogPayload(
        device_id=session.device_id_hex,
        block_number=block_number,
        payload_hash=payload_hash.hex(),
        signature=sign_with_device_key(payload_hash),  # Edge VMDR key
        pq_commitment=mock_pq_commitment(),  # TODO: real ML-DSA-65
        retina_state_commitment=get_visual_oracle_root(),
        retina_w3bstream_enforce=config.trio.validate_on_ingest,
        events_root=events_root.hex(),
        retina_events_root_verify=config.trio.retina_events_root_verify,
        node_id=compute_node_id(session.device_id_hex, session.first_session_id),
        session_root=get_posp_root(),  # optional
        node_session_verify=config.trio.node_session_verify,
    )
    
    # 5. Call WASM
    result = await wasmtime_runner.run(payload)
    
    # 6. Handle result
    if result.exit_code != 0:
        emit_anomaly("trio_retina_validation", result.exit_code, payload)
        if config.trio.validate_on_ingest:
            raise ValidationError(f"trio-retina exit {result.exit_code}")
    
    return ValidationResult(ok=result.exit_code == 0, payload=payload, exit_code=result.exit_code)
```

### Node ID Computation (matches trio-retina standard)

```python
def compute_node_id(device_id_hex: str, first_session_id: str) -> str:
    """SHA-256(QORTROLLER-NODE-v0 || device_id || first_session_id)"""
    data = b"QORTROLLER-NODE-v0" + bytes.fromhex(device_id_hex) + first_session_id.encode()
    return hashlib.sha256(data).hexdigest()
```

---

## Qoresence-Specific Adaptations

| trio-retina (MachineFi) | Qoresence Adaptation |
|-------------------------|---------------------|
| `device_id` = controller VMDR pubkey | Same — DualShock Edge VMDR |
| `block_number` = IoTeX L1 block | Same — RPC to IoTeX testnet/mainnet |
| `pq_commitment` = ML-DSA-65 real | Mock for now; real when ZKSepProof ready |
| `retina_state_commitment` = Visual Oracle root | Qoresence `VisualRuntime` state root |
| `events_root` = Merkle of session events | Qoresence `RetinaEventBus` event batch |
| `node_id` = SHA-256(QORTROLLER-NODE-v0...) | Same format, Qoresence namespace |
| `session_root` = Scorecard/PoSP root | Qoresence `OutcomeRuntime` PoSP root |
| `node_session_verify` = Opt-in gate | Config flag, default OFF |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| WASM execution adds latency | Batch validation (flush_interval_s), async subprocess |
| wasmtime not available in container | Install in Dockerfile; fallback to mock mode |
| ML-DSA-65 not implemented | Mock PQ commitment; real when ZK artifacts ready |
| Block number RPC dependency | Cache latest block; mock in tests |
| Payload format drift | PV-CI invariant gate (INV-W3S-*) |

---

## Testing Strategy

```python
# tests/test_trio_retina.py

class TestTrioRetinaValidator:
    def test_payload_builder(self): ...
    def test_wasmtime_runner_mock(self): ...  # Mock wasmtime returning exit 0
    def test_wasmtime_runner_failures(self): ...  # Inject exit codes 1-8
    def test_node_id_computation(self): ...  # Match trio-retina standard
    def test_integration_with_eventbus(self): ...  # Full flow
    def test_config_flags(self): ...  # validate_on_ingest/flush
```

---

## Configuration Example

```yaml
# docker-compose.yml addition
services:
  qoresence:
    environment:
      - QORESENCE_TRIO_ENABLED=1
      - QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm
      - QORESENCE_TRIO_VALIDATE_ON_FLUSH=1
      - QORESENCE_TRIO_FLUSH_INTERVAL=30
      - QORESENCE_TRIO_BLOCK_RPC=https://babel-api.testnet.iotex.io
      - QORESENCE_TRIO_NODE_SESSION_VERIFY=0
```

---

## Future: Full On-Chain Path

When ready:
1. Register w3bstream project at `console.w3bstream.com`
2. Configure project to call IoTeX settlement contract
3. Enable `node_session_verify=true` + real `pq_commitment`
4. Add `CHAIN_SUBMISSION_PAUSED` flip (operator ceremony)

This document is the **single source of truth** for trio-retina integration into Qoresence.