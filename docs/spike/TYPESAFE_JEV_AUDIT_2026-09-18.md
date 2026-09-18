# TypeSafe / Jev Integration Audit — 2026-09-18

Branch: `feat/jev-audit-hardening` (from `main` @ `#229` glass fix).
Scope: observation-plane packs under `qoresence/observability/` that call
`TypeSafeClient.system_one`, plus CLI/`/health` wiring and look/drive graphs.

Contract (fail closed):

| Rule | Expectation |
|------|-------------|
| Vote not voice | Compact state + Choice/Score/Noul; code owns consequences |
| `licenses_digits: False` forever | Only ConfirmTicket + `score_vlm_locked` license digits |
| Observation plane | No bus emit from packs; no lobe locks on hot path; timer/worker threads |
| Local fallback | Missing key/SDK/API must not break `--play` |
| Confidence | ≥0.7 act, 0.4–0.7 soft, <0.4 observe |
| Key load | `TYPESAFE_API_KEY` or `.secrets/typesafe.key` with `utf-8-sig`; never print |
| Glass | Do not regress TicketGlass/SyncGlass (#229) |

## Inventory

| Pack | Flag / env | `/health` key | Plane |
|------|------------|---------------|-------|
| `jev_conductor.py` | `--jev` / `QORESENCE_JEV=1` | `jev` | observation |
| `noul_observatory.py` | `--noul` / `QORESENCE_NOUL=1` | `noul` | observation |
| `press_labeler.py` | under `--jev` | `press_labeler` | observation |
| `recap_hygiene.py` | under `--jev` (inspect path) | (via recap callers) | observation |
| `sync_coroner.py` | under `--jev` | `sync_coroner` | observation |
| `ticket_stale.py` | `--jev-ticket-stale` / env (or under `--jev`) | `ticket_stale` | observation |
| `ticket_glass.py` | `--ticket-glass` / env (or under `--jev`) | `ticket_glass` | observation |
| `sync_glass.py` | `--sync-glass` / env (or under `--jev`) | `sync_glass` | observation |
| `score_plausibility.py` | under `--jev` | `score_plausibility` | observation |

`--play` does **not** enable any of the above (verified in `cli.py` + config
dataclasses in `qoresence/core/unified_config.py`).

## Checklist results (post-fix)

Legend: **PASS** / **FAIL→fixed** / **N/A**.

| Pack | Default OFF | licenses_digits False | Local fallback | utf-8-sig | Cadence/reuse | Client timeout | Warn-once | Hot-path enqueue-only | No bus.emit | Parse nouls/choices/scores | Tests |
|------|-------------|----------------------|----------------|-----------|---------------|----------------|-----------|-----------------------|-------------|---------------------------|-------|
| ticket_glass | PASS | PASS | PASS | PASS | PASS (~2s ask, 15s reuse) | PASS (10s) | PASS | PASS | PASS | PASS | PASS |
| sync_glass | PASS | PASS | PASS | PASS | PASS | PASS (10s) | PASS | PASS | PASS | PASS | PASS |
| jev_conductor | PASS | PASS | PASS | PASS | **FAIL→fixed** (AskCadence) | **FAIL→fixed** | **FAIL→fixed** | PASS (call-site judge) | PASS | PASS | PASS + helper |
| noul_observatory | PASS | PASS | PASS | PASS | **FAIL→fixed** (AskCadence on worker) | **FAIL→fixed** | **FAIL→fixed** | PASS | PASS | PASS | PASS + helper |
| press_labeler | PASS | PASS | PASS | PASS | PASS* (press-rate, not 250ms) | **FAIL→fixed** | **FAIL→fixed** | PASS (after-worker) | PASS | PASS | PASS + helper |
| recap_hygiene | PASS | PASS | PASS | PASS | N/A (on-demand inspect) | **FAIL→fixed** | **FAIL→fixed** | N/A | PASS | PASS | PASS + helper |
| sync_coroner | PASS | PASS | PASS | PASS | PASS (3s, only when degraded) | **FAIL→fixed** | **FAIL→fixed** | PASS (timer) | PASS | PASS | helper wiring |
| ticket_stale | PASS | PASS | PASS | PASS | PASS (2s timer) | **FAIL→fixed** | **FAIL→fixed** | PASS | PASS | PASS | PASS + helper |
| score_plausibility | PASS | PASS | PASS | PASS | PASS (3s, only on refuse) | **FAIL→fixed** | **FAIL→fixed** | PASS (timer) | PASS | PASS | helper wiring |

\* Press labeling is HID-edge driven; timeout + warn-once close the hang/spam
failure mode without forcing a 2s reuse that would drop distinct presses.

### Highest-priority pre-fix gaps (vs #229 glass)

1. **Bare `TypeSafeClient()`** — no timeout, default SDK retries → hung worker.
2. **`log.debug` only on failure** — silent forever in production logs.
3. **Noul worker** — one `system_one` per dequeued bus record → API spam under
   dense visual traffic (same class as pre-#229 TicketGlass).
4. **Jev conductor** — `judge()` callable from fast-moment / match-agent paths
   without ask backoff.

Glass packs already had timeout / RetryPolicy(max_retries=0) / warn-once /
ask_interval+reuse. **Left untouched** in this PR.

## What this PR changes

### New shared helper — `qoresence/observability/typesafe_ask.py`

- `ensure_typesafe_key()` — env first, else `.secrets/typesafe.key` with
  `utf-8-sig` (never logs the value).
- `open_typesafe_client(timeout_s=10)` — `RetryPolicy(max_retries=0)` when
  available; TypeError fallbacks for older SDKs.
- `system_one(...)` — timeout on client + call; warn-once via mutable flag.
- `AskCadence.ask_or_reuse(...)` — glass-style ask interval + reuse of last
  good answers (default 2s ask / 15s reuse).

### Packs wired to the helper

`jev_conductor`, `noul_observatory`, `press_labeler`, `recap_hygiene`,
`sync_coroner`, `ticket_stale`, `score_plausibility`.

Noul + Jev also use `AskCadence` (default ask interval 2s, reuse 15s).

### Not TypeSafe digit minters

- `qoresence/agents/drive_graph.py` / look-graphs: observation-plane **look
  licenses** (default OFF). Docs (`docs/DRIVE_GRAPH.md`, `docs/LOOK_GRAPHS.md`)
  keep digits on confirm-ticket. **No `system_one` / TypeSafe usage.** Confirmed
  by ripgrep — no Jev mint of digits there.

### Invariants preserved

- `rg 'licenses_digits\s*[:=]\s*True' qoresence/observability` → empty.
- `rg 'bus\.emit|emit_raw' qoresence/observability` → empty (packs).
- TicketGlass / SyncGlass source still local (#229); tests assert they do not
  import `typesafe_ask`.

## Operator prove steps

```bash
# 1) Default --play stays dark on Jev packs
qoresence --play --deck
# GET /health → jev/noul/ticket_glass/sync_glass/... enabled:false

# 2) Opt-in one pack at a time (needs TYPESAFE_API_KEY or .secrets/typesafe.key)
QORESENCE_JEV=1 qoresence --play --deck --jev
# /health.jev.enabled true; licenses_digits false
# Missing key → local_heuristic source, process stays up

QORESENCE_NOUL=1 qoresence --play --deck --noul
# /health.noul — judged climbs; typesafe_asks rate-limited (~2s)

qoresence --play --deck --ticket-glass --sync-glass
# /health.ticket_glass.ask_interval_s ~ 2; sync_glass age_s honest when starved

# 3) Unit smoke
python -m pytest tests/test_typesafe_ask.py tests/test_ticket_glass.py tests/test_sync_glass.py -q
```

## Summary

| Already OK on main | Fixed in this PR |
|--------------------|------------------|
| licenses_digits False everywhere in Jev packs | Shared timeout (10s) + RetryPolicy(max_retries=0) |
| utf-8-sig key load | Warn-once on system_one failure |
| Local heuristic fallback | Noul + Jev ask cadence/reuse |
| Glass #229 cadence/timeout/warn-once | Wiring tests for helper adoption |
| Default OFF; --play does not enable | Audit doc (this file) |
| No bus.emit / no lobe locks on hot path | |
| Drive/look graphs not TypeSafe digit minters | |
