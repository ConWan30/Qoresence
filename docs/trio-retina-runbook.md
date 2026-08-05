# trio-retina Runbook — Operator Procedures

> **Purpose**: Operational procedures for the Qoresence × trio-retina w3bstream validation integration.
> **Audience**: Operators deploying/running trio-retina validation in production.
> **Prerequisites**: Qoresence repo cloned, Docker available, IoTeX testnet access for on-chain path.

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Qoresence Observation Plane (5 Lobes)                                       │
│  Streamer | Controller | Screen | Outcome | Visual                          │
└─────────────────────────┬───────────────────────────────────────────────────┘
                          │ Events → RetinaEventBus
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ trio-retina Validation Layer (Optional)                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────────┐  │
│  │ EvmLogPayload│───▶│ WasmtimeRunner│───▶│ w3bstream Applet (WASM)      │  │
│  │  Builder     │    │  (CLI/Embed)  │    │  handle_poac_payload()       │  │
│  └──────────────┘    └──────────────┘    └──────────────────────────────┘  │
│         │                   │                        │                     │
│         │                   │                        ▼                     │
│         │                   │         ┌──────────────────────────────┐    │
│         │                   │         │ Validation Result (OK/FAIL)  │    │
│         │                   │         └──────────────────────────────┘    │
│         │                   │                        │                     │
│         ▼                   ▼                        ▼                     │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │ TrioRetinaValidator (async, batch flush every 30s default)           │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────────────────────┘
                          │ (Optional) On-chain via w3bstream
                          ▼
              ┌─────────────────────────────┐
              │ w3bstream Project           │
              │ → IoTeX Settlement Contract │
              └─────────────────────────────┘
```

**Key Principle**: Mechanical validation only — format/presence checks, not truth oracle. The gamer remains the agency-holder.

---

## 2. Configuration

### Environment Variables (Production)

```bash
# Core trio-retina
export QORESENCE_TRIO_ENABLED=1
export QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm
export QORESENCE_TRIO_VALIDATE_ON_FLUSH=1
export QORESENCE_TRIO_FLUSH_INTERVAL=30.0

# On-chain path (requires w3bstream project registration)
export QORESENCE_TRIO_BLOCK_RPC=https://babel-api.testnet.iotex.io
export QORESENCE_TRIO_NODE_SESSION_VERIFY=1
export QORESENCE_TRIO_EVENTS_ROOT_VERIFY=1

# PQ Commitment (ZKSepProof)
export QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=real
export VAPI_ZK_ARTIFACTS_DIR=/app/zk_artifacts

# Device Identity (DualShock Edge VMDR)
export QORESENCE_DEVICE_ID_HEX=<64-hex VMDR pubkey hash>
```

### CLI Flags (Equivalent)

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

### Config Precedence

```
CLI flags > Environment variables > Defaults
```

---

## 3. Deployment Procedures

### 3.1 Local Development (Dry-Run)

```bash
# From repo root
python -m qoresence.cli --dry-run --trio \
  --trio-wasm-path=w3bstream_applet.wasm \
  --trio-validate-on-flush

# Expected output:
# [INFO] Trio-retina validation enabled
# [INFO] Presence Fusion Engine initialized
# [INFO] Dry run complete - config valid, lobes initialized
```

### 3.2 Docker Build

```bash
# Build image (takes 5-10 min first run)
docker build -t qoresence:latest .

# Verify image has artifacts
docker run --rm qoresence:latest ls -la /app/w3bstream_applet.wasm /app/zk_artifacts/

# Dry-run in container
docker run --rm qoresence:latest --dry-run --trio \
  --trio-wasm-path=/app/w3bstream_applet.wasm \
  --trio-validate-on-flush
```

### 3.3 Docker Compose (Production)

```yaml
# docker-compose.yml already has trio-retina env vars
# Just ensure .env file has your values:
cat > .env <<EOF
QORESENCE_TRIO_ENABLED=1
QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm
QORESENCE_TRIO_VALIDATE_ON_FLUSH=1
QORESENCE_TRIO_FLUSH_INTERVAL=30.0
QORESENCE_TRIO_BLOCK_RPC=https://babel-api.testnet.iotex.io
QORESENCE_TRIO_NODE_SESSION_VERIFY=1
QORESENCE_TRIO_EVENTS_ROOT_VERIFY=1
QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=real
QORESENCE_DEVICE_ID_HEX=<your-64-hex-device-id>
EOF

docker-compose up -d
```

### 3.4 w3bstream Project Registration (On-Chain Path)

> **Required only for on-chain anchoring**. Skip for local validation only.

1. Go to `https://console.w3bstream.com`
2. Create new project → select "IoTeX" chain
3. Configure applet: upload `w3bstream_applet.wasm`
4. Set settlement contract: IoTeX L1 PoAC verifier address
5. Note Project ID and API Key
6. Add to environment:
   ```bash
   export QORESENCE_TRIO_W3STREAM_PROJECT_ID=<project-id>
   export QORESENCE_TRIO_W3STREAM_API_KEY=<api-key>
   ```

---

## 4. Operational Procedures

### 4.1 Starting a Session with Validation

```bash
# Full session with all lobes + trio-retina
qoresence \
  --session-id=my_session_001 \
  --streamer --controller --outcome --screen --visual \
  --trio \
  --trio-wasm-path=/app/w3bstream_applet.wasm \
  --trio-validate-on-flush \
  --trio-flush-interval=30
```

### 4.2 Monitoring Validation Health

```bash
# Check trio-retina stats via health endpoint
curl http://localhost:8765/health | jq .trio_retina

# Expected response:
{
  "trio_retina": {
    "enabled": true,
    "validator_active": true,
    "validations_total": 42,
    "validations_passed": 41,
    "validations_failed": 1,
    "last_flush_ns": 1234567890123,
    "avg_validation_ms": 148.2
  }
}
```

### 4.3 Logs to Watch

| Log Pattern | Meaning |
|-------------|---------|
| `TrioRetinaValidator: Validation OK` | Normal — payload passed |
| `TrioRetinaValidator: Validation FAILED` | Anomaly — check payload |
| `WasmtimeRunner: exit_code=-1` | WASM execution error (wasmtime missing or WASM corrupt) |
| `TrioRetinaValidator: PQ commitment generation failed` | ZKSepProof artifacts missing or proof generation failed |

### 4.4 Common Failure Modes

| Symptom | Cause | Resolution |
|---------|-------|------------|
| `wasmtime not found` | wasmtime not in PATH | Install wasmtime 16.0.0; verify `which wasmtime` |
| `WASM file not found` | Path mismatch | Check `QORESENCE_TRIO_WASM_PATH` points to valid `.wasm` |
| `snarkjs: command not found` | Node.js/snarkjs missing | Install Node.js 20 + `npm install -g snarkjs` |
| `ZKSepProof artifacts missing` | Artifacts not copied | Verify `VAPI_ZK_ARTIFACTS_DIR` has `.wasm`, `.zkey`, `.json` |
| `Validation timeout` | WASM too slow | Increase flush interval or check wasmtime version |

---

## 5. Chain Submission (Operator-Gated)

> **Triple-Gate Ceremony Required** — see `chain-spend` skill.

### 5.1 Prerequisites

- w3bstream project registered and tested
- IoTeX testnet wallet with IOTX for gas
- `CHAIN_SUBMISSION_PAUSED` env var controls gate

### 5.2 Enable Chain Submission

```bash
# 1. Verify w3bstream project receives payloads
curl -X POST https://babel-api.testnet.iotex.io/v1/projects/<id>/verify \
  -H "Authorization: Bearer <api-key>" \
  -d @sample_payload.json

# 2. Flip gate (operator ceremony)
export CHAIN_SUBMISSION_PAUSED=0

# 3. Restart Qoresence to pick up new env
docker-compose restart qoresence

# 4. Verify on-chain anchoring appears
# Check IoTeX explorer for settlement contract calls
```

### 5.3 Disable Chain Submission (Emergency)

```bash
export CHAIN_SUBMISSION_PAUSED=1
docker-compose restart qoresence
```

---

## 6. PQ Commitment (ZKSepProof)

### 6.1 Mock Mode (Default, No Artifacts Needed)

```bash
# Uses deterministic "a" * 64 commitment
# Suitable for CI/testing without ZK artifacts
export QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=mock
```

### 6.2 Real Mode (Requires ZKSepProof Artifacts)

```bash
# Artifacts must be at VAPI_ZK_ARTIFACTS_DIR:
# - ZKSepProof.wasm
# - ZKSepProof_final.zkey
# - ZKSepProof_verification_key.json

export QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=real
export VAPI_ZK_ARTIFACTS_DIR=/app/zk_artifacts
```

### 6.3 Regenerating ZKSepProof Artifacts

```bash
cd vapi-pebble-prototype/contracts/circuits

# 1. Compile circuit
npx circom ZKSepProof.circom --r1cs --wasm --sym

# 2. Run MPC ceremony (requires coordinator)
bash run-mpc-ceremony.sh ZKSepProof

# 3. Copy to bridge artifacts
cp ZKSepProof_js/ZKSepProof.wasm ../bridge/zk_artifacts/
cp ZKSepProof_final.zkey ../bridge/zk_artifacts/
cp ZKSepProof_verification_key.json ../bridge/zk_artifacts/

# 4. Rebuild Docker image to pick up new artifacts
docker build -t qoresence:latest .
```

---

## 7. Troubleshooting Checklist

### Pre-Flight (Before Session)

- [ ] `python -m qoresence.cli --dry-run --trio` passes
- [ ] `docker run --rm qoresence:latest --dry-run --trio` passes
- [ ] WASM file exists at configured path
- [ ] wasmtime 16.0.0 available (`wasmtime --version`)
- [ ] If real PQ: ZKSepProof artifacts exist at `VAPI_ZK_ARTIFACTS_DIR`
- [ ] If on-chain: w3bstream project responds to test payload

### During Session

- [ ] Monitor `/health` endpoint every 30s
- [ ] Watch for `Validation FAILED` logs
- [ ] Check `avg_validation_ms` < 500ms (batch mode)

### Post-Session

- [ ] Export session JSONL for audit
- [ ] Verify trio-retina stats in final report
- [ ] Archive validation anomalies for review

---

## 8. Rollback Procedures

| Scenario | Rollback |
|----------|----------|
| WASM validation consistently failing | Set `QORESENCE_TRIO_ENABLED=0`, restart |
| PQ commitment generation failing | Set `QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=mock` |
| On-chain anchoring failing | Set `CHAIN_SUBMISSION_PAUSED=1` |
| High validation latency | Increase `QORESENCE_TRIO_FLUSH_INTERVAL` to 60s |

---

## 9. Version Compatibility Matrix

| Qoresence | trio-retina | wasmtime | w3bstream Applet | ZKSepProof |
|-----------|-------------|----------|------------------|------------|
| Current   | 0.3.0+      | 16.0.0   | FROZEN-v1        | v0 (Groth16) |

---

## 10. References

- Integration Design: `docs/trio-retina-integration.md`
- Protocol Invariants: `.claude/skills/protocol-invariants/SKILL.md`
- Chain Spend: `.claude/skills/chain-spend/SKILL.md`
- Capture Rig: `.claude/skills/capture-rig/SKILL.md`
- Biometric Calibration: `.claude/skills/biometric-calibration/SKILL.md`

---

*Generated with [Devin](https://devin.ai)*