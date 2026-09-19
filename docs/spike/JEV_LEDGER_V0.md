# Jev Ledger v0 — unified judgment sink

Source of truth: `docs/OCCF.md` (objects → "Judgment ledger row"; land order #1/#2).
This note is the implementation pointer for slice 1 only.

## What landed

- `qoresence/observability/jev_ledger.py` — append-only JSONL sink.
  Schema `qoresence.jev.ledger.v0`, plane `qoresence-observation`,
  default path `logs/jev_ledger.jsonl` (`QORESENCE_JEV_LEDGER_PATH` overrides).
- API: `append_judgment` / `note_judgment` (dual-write hook packs call),
  `JevLedger` (explicit-path sink for tests/tools), `read_judgments`,
  `configure_jev_ledger` (CLI startup), `reset_jev_ledger` (tests/shutdown).
- Enable: `--jev-ledger` / `QORESENCE_JEV_LEDGER=1`, or under the Jev
  umbrella `--jev` / `QORESENCE_JEV=1`. Default OFF; `--play` does not enable.

## Row shape

```json
{
  "schema": "qoresence.jev.ledger.v0",
  "plane": "qoresence-observation",
  "pack": "ticket_stale",
  "clock_ns": 0,
  "frame_seq": null,
  "licenses_digits": false,
  "verdict": {},
  "ts": 0.0
}
```

`licenses_digits` is False on every row forever and is scrubbed inside the
payload copy too — the ledger never mints scores. Unknown `pack` fails closed:
rejected, nothing written. Append never raises into a pack hot path, never
emits bus events, and takes only the ledger's own lock around the file append.

## PACKS

`ticket_stale`, `noul`, `jev_conductor` (alias `conductor`), `press_labeler`,
`recap_hygiene`, `sync_coroner`, `score_plausibility`, `ticket_glass`,
`sync_glass`, `mint_verifier`, `join_picker`, and reserved `connector`
(OCCF slice 3 — no writer yet).

## Writers in this slice

- Dual-write inside each pack `_write_jsonl`: `ticket_stale`, `noul`,
  `sync_coroner`, `score_plausibility`, `join_picker`, `mint_verifier`
  (ticket-id-scrubbed row), `ticket_glass`, `sync_glass`, `press_labeler`.
- `note_judgment` on verdict paths without a private JSONL: `jev_conductor`
  (`JevConductor.judge`), `recap_hygiene` (`inspect_envelope`).

Private per-pack JSONL is unchanged — the ledger is a second sink, not a
migration.

## Deferred (OCCF land order)

- `--jev-connector` / `qoresence.connector-bind.v0` writer (`pack="connector"`
  is reserved but silent — no lone `connector.jsonl`).
- Thin MCP tools / `jev_tail` on `get_observation`; Muse skill.md.
- Pages / directory listing.
- Migrating packs off private JSONL entirely.
