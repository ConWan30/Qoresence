# Trio → Qoresence Gap Analysis

**Reference:** *Trio: A Three-Tier Foundation System for Physical-World Understanding*, MachineFi Lab, v1.0, June 2026.
**Scope:** Map Trio's five design principles and seven planes to Qoresence's current architecture, identify gaps, and propose a phased adoption plan.

---

## Executive Summary

Trio is an industrial physical-world understanding system (car washes, warehouses) with safety-critical actuation, multi-camera deployments, and regulatory compliance. Qoresence is a single-capture-card sports analytics and commentary system. A wholesale port is neither feasible nor desirable — much of Trio's machinery (scene graphs, PLC integration, safety gates, multi-tenancy, MLOps governance) does not transfer.

However, Trio's **five design principles** are architecturally sound and Qoresence already has a similar tiered structure. Three principles offer high-value, incremental improvements:

| Principle | Trio | Qoresence today | Adoption value |
|-----------|------|-----------------|----------------|
| P1: Symbols flow between tiers | Typed detection bus `X_t` | Event bus with typed `EventType` enum | **Low** — already done |
| P2: Router owns cost | Learned `ρ_t` classifier | Hand-tuned intervals + reason allowlist | **Medium** — formalize must-fire set |
| P3: Bidirectional tool interfaces | `zoom-redetect`, `rollout-wm`, `query-memory` | VLM re-queries frames ad hoc | **Medium** — typed tool registry |
| P4: Evidence-bearing decisions | `(y_t, e_t)` pairs with cited detections | No citation mechanism | **High** — biggest gap |
| P5: Frozen foundations, trained adapters | LoRA per-deployment | No adapter training pipeline | **Low** — out of scope |

---

## Principle-by-Principle Analysis

### P1: Symbols Flow Between Tiers

**Trio:** Every inter-tier interface is a structured, typed, low-dimensional symbolic representation. The detection bus `X_t` carries track IDs, class labels, bounding boxes, confidence scores — never raw pixels or dense features. The only exception is the pass-through of raw frames to the Tier 2 encoder.

**Qoresence today:** The `RetinaEventBus` already enforces typed events via the `EventType` and `SourceLobe` enums. Each event has a `payload: dict[str, Any]` with a documented schema per event type. The `VisualContext` dataclass is a strongly-typed symbolic representation of game state. The `OUTCOME_EVENT` payload carries `event_name`, `profile_id`, `confidence`, and `fields`.

**Gap:** Minor. Qoresence's event payloads are `dict[str, Any]` rather than frozen dataclasses, so schema drift is possible. The `VisualContext.to_dict()` round-trip is the closest thing to a formal data contract.

**Recommendation:** No change needed for now. The existing typed enum + payload pattern is sufficient. If schema enforcement becomes a problem, consider migrating high-frequency payloads to frozen dataclasses with `to_dict()`/`from_dict()`.

---

### P2: The Router Owns Cost

**Trio:** A dedicated, learnable router `ρ_t ∈ {0,1}` is the *sole* mechanism for regulating operational cost. It combines a utility-cost classifier with deployment-specific must-fire predicates:

```
ρ_t = (∃ m ∈ M_must : m(X_t, Z_t) = true) ∨ ρ*_t
```

The router fires on only 2–10% of frames. Must-fire predicates include safety-critical classes, anomaly score thresholds, and operator queries.

**Qoresence today:** The `A2AOrchestrator` gates Gemini/DeepSeek invocation using:
- Per-reason minimum intervals (`_INTERVAL_BY_REASON`)
- A football-only reason allowlist (big-play events bypass the global floor)
- Drive phase gating (`drive_pressure` requires `phase in {pressure, armed, open, active}`)
- Coupling threshold gating (`coupling >= 0.45`)
- A post-hoc menu guard (keyword check on Gemini's scene summary)
- An in-flight flag preventing concurrent cycles

This is a hand-tuned heuristic router, not a learned classifier. The "must-fire" concept exists implicitly (big-play events bypass the floor) but is not formalized as a typed predicate set.

**Gap:**
1. No explicit must-fire predicate set — the logic is scattered across `if` branches
2. No learned utility-cost classifier — intervals are static
3. No counterfactual evaluation (simulating both `ρ=0` and `ρ=1` decisions)
4. No router observability log (which inputs triggered/suppressed reasoning)

**Recommendation (medium value):**
- **Formalize must-fire predicates** as a typed set: `MustFirePredicate` protocol with `check(situation) -> bool`. Register predicates per profile (e.g., NCAA: `touchdown_scored`, `turnover_detected`, `two_minute_warning`).
- **Add a router decision log** to the JSONL event stream: emit a `ROUTER_DECISION` event with `{reason, fired, inputs, interval, last_trigger_age}` for every evaluation, not just fires.
- **Skip the learned classifier** — Qoresence's volume is too low (personal use) to justify training data collection. The hand-tuned intervals work well.

---

### P3: Bidirectional Tool Interfaces

**Trio:** Tier 3 (LLM agent) has a tool registry `T_3` with strict JSON schemas for re-invoking lower tiers:
- `zoom-redetect(region, vocabulary, threshold) → X'_t`
- `rollout-wm(z_t, action_sequence) → ẑ_{t+1:t+H}`
- `query-memory(query, k) → top-k episodes`
- `business-systems(API, params) → response`

Each tool returns a structured object, not free-form text. The agent can make up to K∈[4,8] tool calls before escalation.

**Qoresence today:** The Gemini agent receives a JPEG frame and situation dict, produces a scene proposal. There is no tool registry — the agent cannot re-query the visual lobe with a refined region, query episodic memory, or run a counterfactual. The DeepSeek chat agent receives the scene proposal and produces commentary. Neither agent can call back to lower tiers.

**Gap:**
1. No tool registry — agents are single-shot, not agentic
2. No `zoom-redetect` equivalent (VLM processes whole frame, no region refinement)
3. No `query-memory` equivalent (no episodic memory store)
4. No `rollout-wm` equivalent (no world model, and adding one is out of scope)
5. No depth bound on tool calls

**Recommendation (medium value):**
- **Define a `ToolRegistry` protocol** with typed tool definitions (name, JSON schema, handler function).
- **Implement `query-memory`**: wrap the existing JSONL event log with a simple retrieval API (filter by event type, time range, field values). This is the easiest tool to add and immediately useful for commentary ("earlier in this drive...").
- **Implement `zoom-redetect`**: allow the Gemini agent to request a cropped region re-analysis from the visual lobe. This requires a callback channel from the A2A orchestrator to the visual lobe.
- **Skip `rollout-wm`**: no world model in Qoresence, and adding one is a research project.
- **Add a depth bound** (K=3 tool calls per reasoning cycle).

---

### P4: Every Decision Carries Its Evidence

**Trio:** Every decision `y_t` is accompanied by an evidence chain `e_t = (X*_t, Z*_t, M*_t, P*_t, c_t)`:
- `X*_t`: cited detections (track IDs, timestamps)
- `Z*_t`: cited world-model surprise events
- `M*_t`: cited memory episodes
- `P*_t`: cited policy/SOP documents
- `c_t`: calibrated confidence

Bare decisions without evidence are not valid outputs. The evidence chain enables:
- **Auditability**: operators can trace any decision back to its supporting inputs
- **Falsifiability**: operator overrides can be routed to the correct tier for retraining
- **Active learning**: low-confidence decisions are prioritized for review

**Qoresence today:** No evidence chain mechanism. When Gemini produces commentary like "red zone pressure building," there is no structured citation linking that claim to:
- The specific `VISUAL_CONTEXT` event that detected red zone entry
- The `OUTCOME_EVENT` that fired `red_zone_entry`
- The frame hash and VLM confidence that produced the field position reading
- The controller coupling score that corroborated the visual signal

The closest thing is:
- `VisualContext.raw_response` (truncated VLM output, 500 chars)
- `VisualContext.frame_hash` and `model` (provenance for the VLM call)
- `BaseEvent.causal_parent_ns` (links controller events to screen/outcome)
- `SceneProposal` and `ChatProposal` store `raw_response` and `model`

But none of these are assembled into a structured evidence chain that accompanies the final commentary.

**Gap:** This is the **biggest gap** and the highest-value improvement.

**Recommendation (high value):**
- **Define an `EvidenceChain` dataclass**:
  ```python
  @dataclass
  class EvidenceChain:
      cited_events: list[EventRef]  # references to bus events by (type, clock_ns, source_lobe)
      cited_frames: list[FrameRef]  # references to frame hashes
      cited_fields: dict[str, FieldProvenance]  # field_name → {value, source, confidence, frame_hash}
      confidence: float  # calibrated overall confidence
      policy_refs: list[str]  # cited prompt/SOP rules
  ```
- **Attach `EvidenceChain` to `CommitAct`**: every approved commentary action carries its evidence.
- **Emit `EVIDENCE_CHAIN` events** to the JSONL log for offline audit.
- **Build the chain in the orchestrator**: when assembling the context packet for Gemini, record which events/fields were included. When Gemini returns, parse its output and link it back to the cited inputs.
- **Add a `--audit` CLI flag** that prints the evidence chain for the last N decisions.

---

### P5: Frozen Foundations, Trained Adapters

**Trio:** Foundation models (LLM, world model, detector) are frozen. Per-deployment adaptation uses LoRA/PEFT on small learned components (fusion adapter, router). Training cadences are decoupled: Tier 1 weekly, fusion monthly, Tier 3 quarterly.

**Qoresence today:** No model training pipeline. The VLM (Quicksilver Pro / Gemini) is a cloud API — no local weights to fine-tune. The fusion weights can be calibrated via logistic regression (`calibrate_weights()` in `presence.py`), but this is not a formal adapter training pipeline. Game profiles are configured, not learned.

**Gap:** Large, but **out of scope** for Qoresence's current stage. Qoresence uses cloud VLMs (no local weights), and the personal-use scale doesn't justify a full MLOps pipeline.

**Recommendation:** Skip for now. If Qoresence ever moves to a local VLM (e.g., Qwen3.6-VL on a Jetson), revisit this principle for LoRA-based game-profile adaptation.

---

## Plane-by-Plane Mapping

| Trio Plane | Qoresence Equivalent | Status |
|------------|---------------------|--------|
| Sensing | Streamer lobe (UVC capture) + Controller lobe (HID) | ✅ Done |
| Edge Perception (Tier 1) | Visual lobe (VLM classification) + Screen lobe (OCR/CV) | ✅ Done (VLM replaces CNN detector) |
| Predictive (Tier 2) | — | ❌ Not applicable (no world model) |
| Fusion & Memory | `PresenceFusionEngine` + `CouplingAnalyzer` + `SituationModel` | ✅ Partial (no episodic memory, no router log) |
| Reasoning (Tier 3) | A2A orchestrator → Gemini agent → DeepSeek agent | ✅ Partial (no tool registry, no evidence chains) |
| Action & Integration | Deck UI overlay + Twitch chat + clip buffer | ✅ Done |
| MLOps & Governance | — | ❌ Not applicable (personal use) |

---

## Proposed Adoption Plan

### Phase 7.1: Evidence Chains (P4) — Highest Value
**Effort:** ~2-3 sessions
**Files:** `qoresence/a2a/orchestrator.py`, `qoresence/a2a/types.py`, `qoresence/core/types.py`

1. Define `EvidenceChain` and `EventRef` dataclasses in `a2a/types.py`
2. Build evidence chain in orchestrator's `run_cycle()`:
   - Record which `OUTCOME_EVENT` / `VISUAL_CONTEXT` events were in the situation
   - Record frame hash and VLM confidence for cited fields
   - Record coupling score and controller signals
3. Attach `EvidenceChain` to `CommitAct`
4. Emit `EVIDENCE_CHAIN` event to JSONL log
5. Add `--audit` CLI flag to print last N evidence chains
6. Tests: verify evidence chain is populated, references are valid, confidence is calibrated

### Phase 7.2: Router Must-Fire Predicates (P2) — Medium Value
**Effort:** ~1-2 sessions
**Files:** `qoresence/a2a/orchestrator.py`, new `qoresence/a2a/router.py`

1. Define `MustFirePredicate` protocol: `check(situation: dict) -> bool`
2. Register per-profile predicates (NCAA: touchdown, turnover, two_minute_warning, red_zone_entry; CoD: kill streak, round_end)
3. Replace scattered `if` branches with predicate set evaluation
4. Emit `ROUTER_DECISION` event for every evaluation (fire or suppress)
5. Tests: verify predicates fire on correct conditions, suppress on non-matching

### Phase 7.3: Tool Registry + Query-Memory (P3) — Medium Value
**Effort:** ~2-3 sessions
**Files:** new `qoresence/a2a/tools.py`, `qoresence/a2a/orchestrator.py`, `qoresence/core/event_bus.py`

1. Define `Tool` protocol: `name`, `schema`, `handler`
2. Implement `query-memory` tool: filter JSONL event log by type/time/fields
3. Implement `zoom-redetect` tool: request cropped region re-analysis from visual lobe (requires callback channel)
4. Wire tools into Gemini agent prompt as available function calls
5. Add depth bound (K=3 tool calls per cycle)
6. Tests: verify tool returns structured output, depth bound enforced

### Not Adopted
- **Tier 2 world model** — V-JEPA for sports video is a research project
- **Scene graph** — Qoresence tracks scoreboard state, not physical objects
- **MLOps governance plane** — overkill for personal use
- **Safety gate / actuation** — not applicable to commentary
- **Learned router classifier** — insufficient data volume
- **LoRA adapter training** — cloud VLM, no local weights
- **Multi-tenancy** — single-user system
