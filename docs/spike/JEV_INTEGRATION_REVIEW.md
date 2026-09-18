# Jev / TypeSafe Integration Review — spike/jev-judgment-pack

Review only. Branch `spike/jev-judgment-pack` (from `main`). Scope: how TypeSafe
System One (Jev) is already integrated in `qoresence/observability/` plus the
AGENTS.md rules that constrain it.

SDK in use: `typesafe_sdk` (`TypeSafeClient().system_one(state=..., questions=...)`),
questions built with `Choice` / `Noul` / `Score` primitives. Responses read via
`response.choices` (`.choice`, `.confidence`), `response.nouls` (`.noul`),
`response.scores` (`.score`).

API key: `TYPESAFE_API_KEY` env first, else `.secrets/typesafe.key` loaded into
env without logging. Missing SDK/key/network → local deterministic heuristic.

Plane: every module returns `"plane": "qoresence-observation"` and
`"licenses_digits": False`.

## 1. `qoresence/observability/jev_conductor.py` — `--jev` / `QORESENCE_JEV=1`

Replaces ClutchBot/MatchAgent **text selection** (not generation): Jev picks a
closed template, code fills it.

- **Enable flag**: `JevConfig.enabled` (`--jev`) or `QORESENCE_JEV=1`. `--play`
  does not enable. `make_jev_from_config` returns None when off.
- **State shape**: `{policy, coupling, red_zone, late_close, close, heat_ticket,
  situation, evidence}` — text only; never HDMI crops.
- **Questions** (`conductor_questions()`, one request):
  - `fast_act` (Choice over `FAST_ACTS`: silent / chat_red_zone /
    chat_close_late / chat_input_spike / chat_clutch_window / consider_clip /
    arm_prediction)
  - `observe` (Choice over `OBSERVE_ACTS`: silent / unlabeled / picture_hud /
    board_licensed)
  - `consider_clip` (Noul, speculative "assuming a coupling ticket exists")
  - `arm_prediction` (Noul)
- **Confidence gates** (`compose_conductor`): Choice confidence < 0.5 → silent;
  `board_licensed` requires `board_locked`; `chat_input_spike`/`clutch_window`
  require `heat_ticket`; clip needs noul ≥ 0.7 AND coupling ≥ 0.55 AND
  (red_zone | late_close); arm needs noul ≥ 0.7 AND red_zone AND coupling ≥ 0.5.
- **Local fallback**: `local_heuristic_conductor` — deterministic
  act/observe/nouls from situation fields.
- **licenses_digits**: always False. `scoreline_matches_board` regex-scrubs any
  stated pair that doesn't match the board; `digits_verified` reports it.
- **Off bus/locks/capture**: `judge()` is called by consumers, not subscribed to
  the bus; own `threading.Lock` guards `_last`/stats only — no emit under lock,
  no lobe locks, no capture path. `conductor_preflight` refuses
  truth/humanity/ban/eligibility claims deterministically.

## 2. `qoresence/observability/noul_observatory.py` — `--noul` / `QORESENCE_NOUL=1`

Bus-subscribed observation plane; enqueue-only hot path + worker thread + JSONL.

- **Enable flag**: `NoulConfig.enabled` (`--noul`) or `QORESENCE_NOUL=1`.
- **State shape**: `{parsed, coupling, red_zone, late_close, policy}` — `parsed`
  is the VLM crop JSON slimmed from bus events (`visual`, `scoreboard`,
  `router_decision`, `presence_report`, `controller`, `coupling`).
- **Questions** (`noul_questions()`):
  - Nouls: `grounded_scorebug`, `true_pause`, `clip_presence`,
    `last_good_temptation`
  - Choice: `hud_kind` over `HUD_KINDS` (live_hud / preplay / select_plate /
    menu / loading / no_board)
  - Scores: `board_honesty`, `presence_density` (3 levels each)
- **Confidence gates** (`compose_observatory`): noul ≥ 0.7 = yes, ≤ 0.3 = no,
  ~0.5 = unknown (fail closed); `hud_kind` needs confidence ≥ 0.5;
  `board_speech` in {unlocked, vlm_ungrounded, menu, confirm_ticket, vlm_none}
  — "confirm_ticket" is speech only, tickets still required. Honesty lattice
  weights live in code (`HONESTY_WEIGHTS`); bands ident/ok/amber/void.
- **Local fallback**: `local_heuristic_nouls` — deterministic noul/kind/score
  stand-ins from `parsed` fields.
- **licenses_digits**: False everywhere.
- **Off bus/locks/capture**: `_on_event` only `put_nowait` into a bounded
  drop-oldest queue (AGENTS.md Rule-5 class). Daemon worker `noul-observatory`
  judges and appends `logs/noul/noul.jsonl`. Never emits, never takes lobe
  locks; own lock only guards `_last_compose` stats.

## 3. `qoresence/observability/press_labeler.py` — under `--jev`

Referee for laptop-HID presses the deterministic EA sheet can't label
(mode None or SheetConflict). Outcomes: labeled / eaten / unlabeled.

- **Enable flag**: same `JevConfig` / `QORESENCE_JEV=1` as the conductor.
- **State shape**: `{policy, press{hid_button,frame_seq,clock_ns}, obs{verb,mode},
  picture{phase_before,phase_after,picture_sheet}, conflict, candidate_modes,
  situation}` — joined record only; never raw HID reports or pixels.
- **Questions** (`press_questions(candidate_modes)`):
  - `mode_pick` (Choice over sheet-offered modes + `no_match`)
  - `press_efficacy` (Noul: did the picture respond)
  - `conflict_pick` (Choice: picture / pad / lag / unresolvable)
- **Confidence gates**: mode/conflict picks need confidence ≥ 0.5; efficacy
  ≥ 0.6 = responded, ≤ 0.3 AND real after-evidence = eaten; missing
  after-evidence stays unlabeled. Jev never emits a verb — code re-resolves a
  picked mode through the EA sheet lookup.
- **Local fallback**: `local_press_labels` — never upgrades unlabeled → labeled;
  only real Jev may.
- **licenses_digits**: False.
- **Off bus/locks/capture**: `label_press` runs on the caller; a private
  `press-labeler-after` worker waits ≥0.4 s for a post-press VisualContext
  (identity-compared, latency-corrected) and re-judges with real
  `phase_after`. Verdicts ride later wires via `drain_verdicts` and
  `logs/press_labels/press_labels.jsonl`. No bus subscribe, no emit, no lobe
  locks.

## 4. `qoresence/observability/recap_hygiene.py` — TypeSafe under `--jev`; deterministic checks always run

Observation door on Recap envelopes. Never a seal.

- **Enable flag**: deterministic checks (`unlocked_digit_leak`,
  `dualsense_treated_as_failure`, `truth_dest_named`) run unconditionally;
  `_try_typesafe` only when `QORESENCE_JEV=1`.
- **State shape**: `{envelope, policy}` — the whole recap envelope dict.
- **Questions** (`hygiene_questions()`):
  - Nouls: `digit_leak`, `hid_failure_lie`
  - Choices: `citation` (supports / contradicts / says_nothing),
    `issue_kind` (closed `ISSUE_KINDS` incl. `no_match`)
- **Confidence gates**: nouls ≥ 0.7 upgrade a hold; citation needs confidence
  ≥ 0.5. Hard holds: leak, truth dest, HID-failure lie, citation contradicts.
- **Local fallback**: `local_hygiene_answers` — deterministic noul/kind from the
  same checks.
- **licenses_digits**: False; `"seals": False`.
- **Off bus/locks/capture**: `inspect_envelope` is a pure function called by the
  recap path; no threads, no bus, no locks. Deterministic preflight refuses
  before any model call.

## 5. `qoresence/observability/sync_coroner.py` — under `--jev`

Timer-driven diagnostician: Jev names the bottleneck, code applies only
predeclared `SyncHealth.set_level` mitigations.

- **Enable flag**: `JevConfig` / `QORESENCE_JEV=1`. Daemon thread `sync-coroner`,
  cadence `config.cadence_s` (default 3 s).
- **State shape**: `{policy, sync, hid, video, controller, bus_eps}` — telemetry
  snapshot (`SyncHealth.stats()`, `hid_telemetry.snapshot()`, FrameHub stamp,
  controller runtime emit_eps, bus events/sec).
- **Questions** (`coroner_questions()`):
  - `bottleneck` (Choice over `BOTTLENECKS`)
  - `severity` (Score, 4 levels: smooth / tight / degraded / critical)
  - `transient` (Noul)
- **Confidence gates** (`compose_verdict`): ≥ 0.7 + severity ≥ tight → apply
  mapped level; 0.4–0.7 → at most one soft step (smooth→tight); < 0.4 → observe;
  `transient` noul ≥ 0.7 → `held_transient` (no escalation). De-escalation gated
  on confidence only.
- **Local fallback**: `local_coroner` — reads fps_ratio / video_age_s / emit_eps;
  note emit_eps (coalesced bus emits) is the storm signal, not raw reports_eps.
- **licenses_digits**: False.
- **Off bus/locks/capture**: timer thread only; takes `bus` for `stats()` reads
  but never subscribes, never emits, never acquires lobe locks. JSONL
  `logs/sync_coroner/sync_coroner.jsonl`.

## 6. AGENTS.md Rules 5–6 and TypeSafe mentions

- AGENTS.md contains **no TypeSafe/Jev mentions**. Rules 5–6 define the OTel
  observation-plane contract these modules voluntarily mirror:
  - Rule 5: a bus subscribe callback must **only enqueue** into a bounded
    drop-oldest queue — never block, never emit, never take a lobe lock.
    `NoulObservatory._on_event` follows this exactly.
  - Rule 6: observation-plane recorders may write small JSONL + metrics but must
    never take lobe locks, never emit bus events, never block on network/disk —
    "smoke detector, not a control loop". All five integrations conform;
    SyncCoroner's `set_level` is the only actuation, and it is a predeclared
    local mitigation, not a bus/lock/capture interaction.
- Hard lock invariants (Rules 1–4) are unaffected: none of these modules emit
  bus events at all.

## Wiring summary

- Config: `JevConfig{enabled}` and `NoulConfig{enabled,out_dir,queue_size}` in
  `qoresence/core/unified_config.py`; env loaders `QORESENCE_JEV`,
  `QORESENCE_NOUL`.
- CLI: `--jev`, `--noul` in `qoresence/cli.py`; runtime instantiates
  `make_jev_from_config`, `make_press_labeler_from_config`,
  `make_coroner_from_config` (all under `config.jev`) and
  `make_noul_from_config` (under `config.noul`) — each in its own try/except.
- Health: `/health` exposes `noul`, `jev`, `press_labeler` stats blocks in
  `qoresence/deck/server.py` (both health builders). SyncCoroner exposes
  `stats()` but is not in the health body.
- Shared pattern per module: env/key check → `ask_fn` (test injection) →
  `_try_typesafe` → `local_heuristic_*` → `compose_*` (code-owned policy) →
  `licenses_digits: False`.
