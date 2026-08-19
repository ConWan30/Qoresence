# Release hardening checklist

Pre-market gate for Qoresence. **Does not** change two-speed rules, capture ownership, or Truth-plane claims.

---

## Checklist

| Item | How to verify |
|------|----------------|
| Deck binds loopback only | `DECK_HOST == "127.0.0.1"` · `pytest tests/test_security_localhost.py` |
| No secrets in git | `.gitignore` has `.env`, `.secrets/`, `*.key`, `logs/`, `clips/` |
| Unit gate | `pytest tests/test_security_localhost.py tests/test_soak_synthetic.py -q` |
| A2A offline | `pytest tests/test_a2a_policy.py -q` |
| Latency opt-in | `QORESENCE_LATENCY_LOG=1` → JSONL under `logs/latency/` |
| CI hardening | `.github/workflows/ci-hardening.yml` on `main` |
| Local preflight | `python scripts/check_release_hardening.py` |
| OTel non-blocking | `pytest tests/test_otel_exporter.py -q` — subscriber must only enqueue; no lock, no bus emit, no network on bus thread |

---

## Latency (opt-in)

```powershell
$env:QORESENCE_LATENCY_LOG = "1"
python -m qoresence.cli --play --deck --streamer-device <N>
# → logs/latency/latency_*.jsonl
# GET /health → "latency": { enabled, names: { ivc_tick, fast_moment, ... } }
```

Wired best-effort (never raises into capture):

- IVC tick → `record_latency("ivc_tick", ms, frame_seq=…)`
- FastMoment → `record_latency("fast_moment", ms)`

---

## Security

- Default Deck host remains **`127.0.0.1`**
- Do **not** ship `0.0.0.0` as default
- Quicksilver / Twitch keys only under `.secrets/` (gitignored)

---

## Soak

`tests/test_soak_synthetic.py` runs a bounded synthetic load:

- 200+ timeline events + DriveGraph summary  
- A2A stub cycles under policy (no invented scorelines)  
- LatencyStats enabled/disabled paths  

Not a multi-hour live soak — a CI-safe regression soak.

---

## Operator pre-release

```powershell
python scripts/check_release_hardening.py
python -m pytest tests/test_security_localhost.py tests/test_soak_synthetic.py tests/test_a2a_policy.py -q
# manual: Pattern B physical card, --play --deck, confirm scores stabilize, A2A optional
```
