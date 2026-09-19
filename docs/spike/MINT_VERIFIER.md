# Mint verifier v0 — frozen design (NON-CLAIM)

Status: **v0 observation pack** under `--jev` / `--mint-verifier`.
Jev is a second clock over evidence on the confirm path. Code owns
ConfirmTicket, SEQGATE, and digit paint.

Grounded in TypeSafe [citation check](https://docs.typesafe.ai/cookbooks/citation_check.md),
[speculative fan-out](https://docs.typesafe.ai/patterns/fan-out.md), and
[confidence-gated routing](https://docs.typesafe.ai/patterns/confidence-routing.md).

## Hard laws (immutable)

1. `licenses_digits: false` on every output forever.
2. Confirm ticket + `score_vlm_locked` remain the **only** path that may paint score digits.
3. Jev may recommend remint or blank. It may never unlock or mint digits.
4. Jev cannot talk down a deterministic refuse (`implausible_transition`, `zero_zero`, empty crop_hash, identity swap).
5. Observation plane: `_on_event` only enqueues; worker never emits bus events, never takes a lobe lock, never blocks capture/HID.
6. State is text/JSON only — no JPEG, no crop bytes.
7. `--play` alone does not enable. Local heuristic if SDK/key missing.

## Enable

- `--mint-verifier` / `QORESENCE_MINT_VERIFIER=1`
- or under `--jev` / `QORESENCE_JEV=1`
- Cadence: 2.0s (`QORESENCE_MINT_VERIFIER_CADENCE`)
- JSONL: `logs/mint_verifier/mint_verifier.jsonl`
- Health: `/health` → `mint_verifier`

## Compose (code owns this)

Gates: ACT 0.7 / SOFT 0.4. Noul probability is the gate.

| Condition | Action |
|---|---|
| No ticket | observe |
| Deterministic refuse in `gate_reason` | blank |
| `hud_kind` in menu / select_plate / loading (conf ≥ SOFT) | blank |
| `same_game` ≤ 0.3 | blank |
| scorebug ≥ ACT and pair matches ≥ ACT | hold |
| scorebug ≥ ACT and pair differs and legal_transition ≥ ACT | remint |
| scorebug ≤ 0.3 | **observe** (do not remint empty ticks) |
| else | observe |

`hold` is a no-op on the mint path. `blank` is advisory speech in v0 (TicketGlass still owns paint veto). `remint` actuation is **not** in v0 (`--mint-verifier-actuate` later).

## Questions (one System One request)

| ID | Type | Speculative |
|---|---|---|
| `same_game` | Noul | no |
| `scorebug_in_crop` | Noul | no |
| `pair_matches_ticket` | Noul | no |
| `legal_transition` | Noul | yes — ignore unless pairs differ |
| `hud_kind` | Choice | no |

Digits in state are already ticketed or observed. Jev compares them; it does not invent a pair.

## Explicitly rejected

- Feeding this into pickBoard or a second paint veto
- JPEG in TypeSafe state
- Consulting the verifier on the VLM `_run` mint thread
- Generated scorelines
