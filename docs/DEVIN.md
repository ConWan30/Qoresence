# Qoresence — Devin.ai Implementation Directive & Roadmap

This document is the single source of truth for Devin.ai CLI (and any human collaborator) to bootstrap and implement Qoresence.
Follow it exactly. Do not invent Truth-plane claims, do not touch any PoAC / FROZEN surface, and keep every lobe default-OFF.

---

### 1. Project Identity

**Name:** Qoresence
**Umbrella:** VAPI
**Relationship to QorTroller:** Independent observation-plane product. Optional thin adapter later. Never a sub-module of QorTroller.

**One-sentence purpose:**
A background presence engine that synchronizes a gamer's controller inputs with their live video feed (capture card or OBS Virtual Cam) and produces gamer-owned causal presence evidence.

**Non-negotiable rules:**
- Observation plane only.
- All lobes default to `enabled = False`.
- Never claim humanity, eligibility, or "anti-cheat".
- Every event must carry `session_id` + `clock_ns`.
- Eye-check is mandatory for any video source.
- NCAA Football 27 and Call of Duty (and future titles) are equal first-class Outcome profiles.

---

### 2. Prerequisites (must be true before any code is written)

**Human side (you):**
- Create the empty GitHub repository: `Qoresence` (or `vapi-qoresence`) under the appropriate organization/account.
- Add Devin / the service account as a collaborator with write access if required by your Devin setup.
- Have a local working directory ready (Devin will create the project folder inside it).

**Environment side:**
- Python ≥ 3.11
- `git`
- Ability to create virtualenvs
- Optional later: OpenCV, websockets, onnxruntime, etc. (installed only when a lobe needs them)

**QorTroller side (compatibility only):**
- Qoresence must never import or depend on QorTroller at runtime in its core path.
- An optional adapter may later accept:
  - an already-minted `session_id`
  - a device identity
  - an attested HID window
- No shared database, no shared FROZEN tags, no shared PoAC wire.

---

### 3. Local Folder & Repository Bootstrap (Devin must do this first)

When the human says the GitHub repo is ready, Devin must execute:

```bash
# 1. Create local project folder
mkdir -p Qoresence
cd Qoresence

# 2. Initialize git and connect to the remote the human just created
git init
git remote add origin <HUMAN_PROVIDED_REPO_URL>
git branch -M main

# 3. Create the exact folder structure below
mkdir -p qoresence/core
mkdir -p qoresence/lobes
mkdir -p qoresence/fusion
mkdir -p qoresence/outputs
mkdir -p qoresence/adapters
mkdir -p tests
mkdir -p docs
mkdir -p tools/obs
mkdir -p scripts

# 4. Create initial files
touch README.md
touch LICENSE
touch pyproject.toml
touch .gitignore
touch docs/ARCHITECTURE.md
touch docs/ROADMAP.md
touch docs/DEVIN.md          # this document itself
touch qoresence/__init__.py
touch qoresence/core/__init__.py
```

Then commit the skeleton with message:
`chore: initial Qoresence skeleton + architecture contract`

---

### 4. Target Folder Structure (must be respected)

```text
Qoresence/
├── README.md
├── LICENSE
├── pyproject.toml
├── .gitignore
├── docs/
│   ├── ARCHITECTURE.md
│   ├── ROADMAP.md
│   └── DEVIN.md                 ← this file
├── qoresence/
│   ├── __init__.py
│   ├── core/
│   │   ├── unified_config.py    ← Phase 1
│   │   ├── session.py           ← Phase 2
│   │   ├── event_bus.py         ← Phase 2
│   │   └── types.py
│   ├── lobes/
│   │   ├── controller.py
│   │   ├── streamer.py          ← UVC / OBS Virtual Cam
│   │   ├── screen.py
│   │   ├── outcome.py           ← NCAA Football 27 + CoD + future profiles
│   │   └── visual.py
│   ├── fusion/
│   │   └── presence.py
│   ├── outputs/
│   │   ├── jsonl.py
│   │   ├── websocket.py
│   │   └── receipt.py
│   └── adapters/
│       └── qortroller.py        ← optional, later
├── tools/obs/
│   └── presence_overlay.html
├── scripts/
│   └── run_qoresence.py
└── tests/
```

---

### 5. Implementation Roadmap (strict order)

#### Phase 0 — Skeleton (immediate)
- Create the folder structure and empty modules listed above.
- Write a clear README that states the purpose, non-claims, and plane separation.
- Acceptance: `git status` is clean, remote is set, README renders correctly.

#### Phase 1 — Unified Config (foundation stone)
**File:** `qoresence/core/unified_config.py`

Must contain:
- `RetinaUnifiedConfig` dataclass
- Nested `OutcomeConfig` + `GameProfile`
- First-class profiles for:
  - `ncaa_football_27` (snap, down_advanced, first_down, score_changed, playclock_reset, quarter_changed, possession_changed)
  - `call_of_duty` (kill, death, assist, streak)
- All lobe enable flags default to `False`
- `session_id`, `session_head_ns`, `device_id_hex`
- Fusion weights
- `eye_check_required: bool = True`
- `never_claim_humanity: bool = True`
- `validate()` method that enforces the contract

Acceptance:
- Unit tests prove every lobe defaults to OFF.
- Validation rejects missing `session_id` or non-positive `session_head_ns`.
- NCAA Football 27 and Call of Duty profiles are present and documented.

#### Phase 2 — Session Authority + Event Bus
**Files:** `qoresence/core/session.py`, `qoresence/core/event_bus.py`, `qoresence/core/types.py`

- `SessionAuthority.mint()` → returns `(session_id, session_head_ns, device_id_hex)`
- `RetinaEventBus` that:
  - Accepts only events carrying `session_id` + `clock_ns` + `source_lobe`
  - Writes JSONL
  - Serves WebSocket (default `127.0.0.1:8765`)
- Synthetic multi-lobe test that proves shared identity and clock

Acceptance: synthetic test passes; one JSONL file and one WebSocket stream contain events from multiple fake lobes with identical `session_id`.

#### Phase 3 — Streamer Lobe (first real user value)
- UVC / OBS Virtual Cam capture
- Eye-check gate
- Emits `activity`, `frame_stats`, `zone` onto the bus
- Basic OBS Browser Source HTML in `tools/obs/`

#### Phase 4 — Controller Lobe + minimal causality
- Local HID → controller events
- Rolling buffer + `causal_parent_ns` stamping

#### Phase 5 — Outcome Lobe with NCAA Football 27 + CoD profiles
- Profile loader
- Event emission according to the catalog defined in Phase 1

#### Phase 6 — Presence Fusion Engine
- Consumes the bus
- Produces `PresenceReport` with `presence_sync_ok` and the weighted verdict

#### Phase 7 — Packaging & optional QorTroller adapter
- Background entry point
- System-tray / status (minimal)
- Optional adapter that can accept an external attested session

---

### 6. QorTroller Synchronization Surface (compatibility only)

Qoresence core must remain runnable with zero knowledge of QorTroller.

Later optional adapter (`qoresence/adapters/qortroller.py`) may accept:
- Pre-minted `session_id`
- Device identity
- Attested HID window / event stream

It must never:
- Import QorTroller packages at module level in the core path
- Write to any PoAC or FROZEN structure
- Change the default-OFF posture of any lobe

---

### 7. Immediate Devin Execution Prompt

Copy-paste the following to Devin once the GitHub repository exists:

```text
Follow docs/DEVIN.md exactly.

1. Create the local folder Qoresence and the full directory structure defined in section 3 and 4.
2. Initialize git, set the remote to the repository I just created, and make the initial skeleton commit.
3. Implement Phase 1 completely: qoresence/core/unified_config.py with RetinaUnifiedConfig, OutcomeConfig, GameProfile, and the two first-class profiles (ncaa_football_27 and call_of_duty). All lobes default to False. Include validate().
4. Write unit tests that prove the defaults and validation rules.
5. Update README.md and docs/ARCHITECTURE.md to match the contract in DEVIN.md.
6. Stop after Phase 1 is green. Do not start Phase 2 until I confirm.
```

---

### 8. Success Criteria for Foundation

After Phase 1 the repository must contain:
- Clean skeleton
- Fully typed, validated `RetinaUnifiedConfig` with NCAA Football 27 and Call of Duty as equal citizens
- Tests proving the safety defaults
- Documentation that any future Devin session (or human) can continue from without re-deriving the architecture

This keeps Qoresence in perfect sync with the observation-plane design while leaving QorTroller's Truth plane completely untouched.