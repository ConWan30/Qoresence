# Optical Title-Presence · r02 Interface & Schema Design

**Repo:** ConWan30/Qoresence  
**Phase:** r02 only — non-executable. No runtime activation.  
**Stamp:** 20260816_093115  
**Incumbent:** `GameAutoDetector` in `qoresence/game_detection.py` — harden/wrap, do not replace.

Observation plane only. Default-OFF. Fail-closed. Prefer no claim over an unstable claim.

---

## Honesty rails (read first)

**F2 — live `--play` status (verified from `qoresence/cli.py` + `unified_config.py`):**  
`GameDetectionConfig.enabled` defaults **False**. `--play` turns on streamer + visual + outcome; it does **not** set `game_detection.enabled`. Auto-enable happens under `--stream` (`enabled=getattr(args, "game_detect", True)`) or explicit `--game-detect`. `--no-game-detect` forces off.  
**Do not claim the detector is always-on under default `--play`.** Status: **deployed-verified OFF unless those flags**.

**F4 — plane field:** every observation record in this schema **must** carry hard `plane: "qoresence-observation"`. Policy comments are not enough.

**Frame path today (deployed-verified):** `cli.connect_lobes` sets  
`game_detector.set_frame_provider(self.streamer.get_current_frame)`  
(or `screen.get_current_frame`). That is the streamer-owned buffer, not a second DShow open.  
`qoresence/monitor/frame_hub.py` is the subscriber slot (`get_latest` / `get_latest_stamp`) used by Deck/IVC. r02 prefers future wrap to **read FrameHub** so the detector never becomes a second owner. Screen-lobe fallback is a different aperture; title-presence wrap should refuse screen as the physical-card source unless the operator later gates it.

---

## A. Observation-record schema (minimal)

Name: **`TitlePresenceObservation`** (design type; not implemented).

Emitted as `payload` of a bus event (see §B). Null-safe: every identity field may be `null` when `claim` is false.

| Field | Type | Rule |
|---|---|---|
| `plane` | const `"qoresence-observation"` | **Mandatory (F4).** Emit rejected if missing or any other value. |
| `session_id` | string | Same as `RetinaEventBus.session_id` / `BaseEvent.session_id`. |
| `clock_ns` | int | Monotonic ns at emit (`qoresence.core.clock_ns` / FrameHub stamp). |
| `session_head_ns` | int \| null | Existing session head. |
| `source_lobe` | `"fusion"` | Aligns with incumbent `SourceLobe.FUSION` on `game_detected`. |
| `claim` | bool | `true` only if FSM state is `locked` **and** `confidence >= fail_closed_threshold`. Otherwise `false`. |
| `profile_id` | string \| null | Optical title key (`ncaa_football_27`, `madden_27`, `call_of_duty`, …). **null if `claim` is false.** |
| `display_name` | string \| null | Human label from incumbent vocab. null if no claim. |
| `title_family` | `"football"` \| `"shooter"` \| `"unknown"` \| null | Coarse family only. Not a score, not a team. |
| `confidence` | float 0.0–1.0 | Incumbent fused score (`GameDetectionResult.confidence`). |
| `fail_closed_threshold` | float | Copy of detector threshold (default **0.65** today). |
| `evidence_count` | int | Window size at emit. |
| `vlm_confidence` | float | Passthrough from incumbent. |
| `ocr_confidence` | float | Passthrough. |
| `motion_confidence` | float | Passthrough. |
| `hysteresis_state` | `"unknown"` \| `"transitioning"` \| `"overlay-rejected"` \| `"locked"` | FSM at emit. |
| `consecutive` | int | Incumbent `_consecutive_detections`. |
| `stability_count` | int | Incumbent `_stability_count` (default 2). |
| `provenance` | object | See below. |
| `no_claim_reason` | string \| null | Required when `claim` is false: `below_threshold` \| `not_locked` \| `overlay_rejected` \| `no_frame` \| `feature_off` \| `plane_invalid`. |

**`provenance` object**

| Field | Meaning |
|---|---|
| `frame_source` | `"framehub"` preferred; `"streamer_latest"` is today's incumbent path; `"none"` if no frame. |
| `sampling_mode` | `"sparse"` (default) or `"lock_verify"` (raised-rate window). |
| `seq` | FrameHub sequence if available, else null. |
| `frame_clock_ns` | FrameHub `clock_ns` if available, else emit `clock_ns`. |
| `poll_interval_s` | Configured poll at emit time. |

**No-claim / null-safe shape (canonical):**

```json
{
  "plane": "qoresence-observation",
  "session_id": "<sid>",
  "clock_ns": 0,
  "session_head_ns": null,
  "source_lobe": "fusion",
  "claim": false,
  "profile_id": null,
  "display_name": null,
  "title_family": null,
  "confidence": 0.0,
  "fail_closed_threshold": 0.65,
  "evidence_count": 0,
  "vlm_confidence": 0.0,
  "ocr_confidence": 0.0,
  "motion_confidence": 0.0,
  "hysteresis_state": "unknown",
  "consecutive": 0,
  "stability_count": 2,
  "provenance": {
    "frame_source": "none",
    "sampling_mode": "sparse",
    "seq": null,
    "frame_clock_ns": null,
    "poll_interval_s": 3.0
  },
  "no_claim_reason": "no_frame"
}
```

**Not in the record (forbidden):**  
humanity, eligibility, PoAC, on-chain refs, wallet, HID raw, IMU, score digits, team names, player nameplates, Twitch, Quicksilver keys, research-ingredient blobs.

---

## B. Bus contract

**Existing (deployed-verified):**  
`GameAutoDetector._emit_game_detected` → `bus.emit_raw(source_lobe=SourceLobe.FUSION, event_type=EventType.GAME_DETECTED, payload={profile_id, display_name, confidence, evidence_count, vlm/ocr/motion_confidence})`.  
**No `plane` field today.** Consumers: `SituationModel._handle_game_detected` (sets `game_profile`), `OutcomeRuntime._on_game_detected` (may `set_game_profile` + `session_start`), ClutchBot / moment scorer.

**Choice: wrap, do not supersede.**

| Event | When | Payload |
|---|---|---|
| `game_detected` (keep `EventType.GAME_DETECTED`) | Only when `claim==true` and state `locked` | **Additive:** existing keys **plus** `plane` and a nested `title_presence` record (full schema). Old readers ignore extras. |
| `title_presence` (**proposed** `EventType.TITLE_PRESENCE = "title_presence"`) | Sparse: on state change, including no-claim transitions | The observation record as payload. New consumers only. |

Justification: outcome/situation already key off `game_detected`. Replacing it would break `--play` identity stick without a migration. Parallel `title_presence` carries the structural plane tag and no-claim shape; wrapping `game_detected` adds the same `plane` when a claim is actually made.

**Forbidden**

- Second DShow / capture-card open. Frame provider = FrameHub subscribe or existing streamer `get_current_frame` only.
- Write into any truth-plane / QorTroller / PoAC store (none exists here; do not invent one).
- Automatic profile authority when title-presence feature is OFF.
- Emitting `claim:true` from `unknown`, `transitioning`, or `overlay-rejected`.
- Mutating a prior observation record in place.

**Profile switch:** incumbent `set_profile_switch_callback` today calls `outcome.set_game_profile` when a detection emits. That is a **callback**, already gated by `game_detection.enabled`. r02 does not grant new authority. Later wrap may fire the callback only from `locked` + `claim` + feature ON.

---

## C. Re-wrapping ceremony interface (undeployed)

Interface only. Must not exist as a live import path in r02.

```
wrap_observation_for_plane(
    record: TitlePresenceObservation,
    dest_plane: str,
    operator_grant: OperatorGrant,
) -> WrapRefuse | WrapEnvelope
```

**Fail-closed rules**

1. If `record.plane != "qoresence-observation"` → `WrapRefuse(reason="plane_mismatch")`.
2. If `dest_plane == "qoresence-observation"` → refuse (not a wrap).
3. If `dest_plane` not in an operator-allowlist (empty by default) → refuse.
4. If `operator_grant` missing, expired, or feature OFF → refuse.
5. If `record.claim` is false → refuse (do not wrap a no-claim).
6. Success produces a **new** envelope: `{plane: dest_plane, source_plane, source_hash, wrapped_at_ns, grant_id}` that **points at** the original bytes. The original record is not mutated.

`source_hash` = SHA-256 of canonical JSON of the observation record (sorted keys, no research sidecar).

**Undeployed by design.** No QorTroller composition in this packet. Dual-plane is structural: wrap cannot rewrite `record.plane`.

---

## D. Hysteresis FSM

States (required): `unknown` | `transitioning` | `overlay-rejected` | `locked`

Incumbent today: `_consecutive_detections` + `_last_emitted_profile` + `_confidence_threshold` + `_stability_count` (default 2). Emit when `consecutive == stability_count` after `confidence >= threshold`. Below threshold resets consecutive to 0. No overlay gate.

| State | Incumbent mapping | Enter | Exit | Emit claim? |
|---|---|---|---|---|
| `unknown` | `consecutive==0`, no last profile or after reset | start; confidence drop; no frame | first above-threshold tick | **no** |
| `transitioning` | `0 < consecutive < stability_count` or profile ≠ last locked | above-threshold tick; profile change | reach stability **or** drop / overlay | **no** |
| `overlay-rejected` | **new** — would have counted but `VisualContext.game_state` in `{menu, lobby, hub, paused}` or ticker-only / no gameplay HUD | overlay evidence while otherwise title-like | gameplay state returns | **no** |
| `locked` | `consecutive >= stability_count` and same `profile_id` | lock-and-verify success | title change, confidence drop, overlay | **yes** (`claim=true`) |

**Fail-closed:** only `locked` emits `game_detected` and `claim:true`. All other states may emit `title_presence` with `claim:false` and a `no_claim_reason`.

Overlay uses existing `VISUAL_CONTEXT` / `VisualContext.game_state` already produced by the detector's vision stack — not a new capture.

---

## E. Event-driven sampling (design only)

**Default (sparse):** keep or *raise* the incumbent `poll_interval_s` (today 3.0s). Non-goal: continuous high-res. No 60 Hz VLM.

**Raise to `lock_verify` (short window, then back to sparse):**

1. Operator `--game-profile` change or first visual lock.  
2. `game_state` transition menu/hub → gameplay.  
3. First `score_vlm_locked` true this session.  
4. Play-phrase SNAP / SPRINT (existing observation sync; not authorship).  
5. Fused title flip vs last locked `profile_id`.

**Stay sparse when:** `locked` and title unchanged; `unknown` with no frame; feature OFF.

---

## F. Research ingredients

**DEFERRED.** Incumbent `learning_enabled` JSONL (`game_detection_learning.jsonl`) is a local sample log, default OFF — not a research-ingredient graph. r02 does not add `source_hash` mutation of the optical record. If a later phase links research: sidecar only, immutable, `source_hash` + decay, never rewrite the observation record.

---

## G. Numbered attackable claims

**C1 — Hard `plane` is mandatory on every observation record.** Residual: `game_detected` payloads today have no plane; old JSONL will not backfill. Tag: **undeployed** (schema), incumbent emit **deployed-verified without plane**.

**C2 — Feature is default-OFF; `--play` does not enable `GameAutoDetector`.** Residual: `--stream` still auto-enables detect unless `--no-game-detect`; operators may confuse presets. Tag: **deployed-verified**.

**C3 — Wrap `game_detected`; add parallel `title_presence`.** Residual: two events can drift if wrap is partial. Tag: **undeployed**.

**C4 — Profile switch stays a callback, not silent authority.** Residual: today's callback already switches Outcome when detect emits; enabling `--game-detect` *is* the operator gate. Tag: **deployed-verified** (callback), wrap discipline **undeployed**.

**C5 — Frame source is streamer-owned; future wrap prefers FrameHub `get_latest`.** Residual: detector today calls `streamer.get_current_frame` directly (same owner, not dual-open). Screen fallback is a different aperture. Tag: incumbent path **deployed-verified**; FrameHub-only wrap **undeployed**.

**C6 — Only `locked` emits `claim:true`.** Residual: overlay-reject depends on `game_state` quality; huddle-as-menu has bitten CFB before (`effective_game_state`). Tag: FSM **undeployed**; huddle fix **deployed-verified** elsewhere.

**C7 — Fail-closed threshold stays the incumbent 0.65 unless config says otherwise.** Residual: local VLM vs Gemini scores are not calibrated to each other. Tag: **emulated** (numeric reuse, no new calibration).

**C8 — No-claim shape never invents `profile_id`.** Residual: consumers that treat any `game_detected` as truth must not receive it on no-claim (hence no `game_detected` unless locked). Tag: **undeployed**.

**C9 — Re-wrapping ceremony is interface-only and fail-closed.** Residual: a future implementer might mutate `plane` in place. Contract forbids it. Tag: **undeployed**.

**C10 — Sampling stays sparse by default.** Residual: lock-verify triggers could be too chatty if wired to every HID edge. Tag: **undeployed**.

**C11 — Research ingredients are deferred; optical record stays unmutated.** Residual: existing learning JSONL could be mistaken for an ingredient graph. Tag: learning file **deployed-verified** as optional log; ingredient model **undeployed**.

**C12 — No scores/names in the title-presence record.** Residual: `VISUAL_CONTEXT` on the same bus still carries board fields; consumers must not fold those into this record. Tag: **undeployed** (this schema); visual context **deployed-verified** separately.

---

## H. Honesty structure + HOLD

| Done in r02 | Emulated / partial | Undeployed |
|-------------|--------------------|------------|
| Incumbent located (`game_detection.py`, emit, stability counter) | Numeric threshold reused without new calibration (C7) | `TitlePresenceObservation` type |
| F2 `--play` vs `--stream` / `--game-detect` wiring read from `cli.py` | Streamer `get_current_frame` treated as same-owner as FrameHub | `EventType.TITLE_PRESENCE` |
| F4 plane field specified | Overlay-reject mapped onto existing `game_state` | FSM wrapper around `_consecutive_detections` |
| Bus wrap-not-supersede chosen against live consumers | | FrameHub-only provider swap |
| Ceremony interface specified fail-closed | | Any live wrap / QorTroller path |
| Sampling triggers listed (design) | | Raised-rate lock-verify |
| Research deferred explicitly | | Implementation, lobe activation |

**Operator HOLD (r02)** — clear these before r03 or any implementation:

1. Accept **wrap** (`game_detected` kept + additive `plane` / nested record) rather than replacing `GAME_DETECTED`?  
2. Accept proposed event name `title_presence` / `EventType.TITLE_PRESENCE`?  
3. Confirm FrameHub `get_latest` as the **preferred** future provider, with today's `streamer.get_current_frame` allowed as equivalent same-owner path until swapped?  
4. Confirm overlay-reject uses existing `VisualContext.game_state` (including the huddle `effective_game_state` rule) rather than a new menu model?  
5. Confirm research ingredients stay **deferred**?  
6. Confirm title-presence remains **default-OFF** and is **not** implied by `--play` (explicit `--game-detect` or a new dedicated flag later)?  
7. Confirm re-wrapping stays undeployed — no QorTroller ceremony in r03/I2?

---

**STOP.** No r03. No Python runtime changes. Await HOLD clearance.
