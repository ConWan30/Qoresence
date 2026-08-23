# Agent Society — narrow agents on the local glass (default OFF)

Agent Society is an optional layer of **role-specialized agents** that sit on AgentGlass / Foundry / timeline. They use **Quicksilver** (same provider family as ClutchBot A2A: DeepSeek + Gemini slots) for **phrasing and reasoning only**.

The *package* is default OFF. `--play` does **not** turn it on. Pass `--agent-society` (or `--agent-society-roles`) to opt in.

They are **not** ClutchBot, **not** a Twitch poster, and **not** a capture owner.

## Enable

```powershell
python -m qoresence.cli --play --deck --controller --streamer-device 0 --streamer-fps 30
# Society stays off

python -m qoresence.cli --play --deck --agent-society
# opt-in: all known roles (rules-only if no Quicksilver key)
```

Or set env:

```powershell
$env:QORESENCE_AGENT_SOCIETY = "1"
$env:QORESENCE_AGENT_SOCIETY_ROLES = "spam_warden,pilot_auditor,drive_coach,ghost_editor,prediction_steward"
```

Without a key, roles run **rules-only** (no crash).

One-shots (no `--play`):

```powershell
python -m qoresence.cli --society-audit
python -m qoresence.cli --society-propose-cuts
```

## Roles

| Role | Job | Side effects |
|------|-----|----------------|
| `spam_warden` | De-dupe / digit soft-path veto advice | Receipt + optional timeline |
| `pilot_auditor` | Session closeout metrics → notes | File/JSON audit |
| `drive_coach` | Post-drive ≤3 bullets | Timeline/Deck note |
| `ghost_editor` | Propose local cut in/out + title | Proposal only (Ghost Cut, not LTX) |
| `prediction_steward` | Draft prediction text when armed | Draft only; resolve stays confirm path |

## Invariants

1. Default OFF
2. No DShow/HDMI open
3. No score digits unless `score_vlm_locked` and values match situation
4. No direct Twitch API from society package
5. Background only — never block grabber/IVC
6. Observation-plane language only

## vs A2A vs ClutchBot

| Layer | Purpose |
|-------|---------|
| ClutchBot | Live Deck / clutch-feed acts (fast/confirm) |
| A2A | Sparse scene↔chat negotiate under policy |
| Agent Society | Ops agents: warden, auditor, coach, editor |
| AgentGlass/MCP | Tool socket for external IDEs/agents |

## Quicksilver

Uses the same provider configuration style as A2A (`QORESENCE_QUICKSILVER_*` / `.secrets`).

| Slot | Model | Job |
|------|-------|-----|
| **Vision / confirm** | `gemini-3.5-flash-lite` | See the board and scene. Lock `score_vlm_locked`. Society must not invent scores until that lock is set. |
| **Reason / phrasing** | `nemotron-3.5-lightning` | Rewrite notes after Gemini has confirmed. Never the eyes. |

Roles that do not need phrasing stay rules-only (`spam_warden`).
