# Agent Society — narrow agents on the local glass (default OFF)

Agent Society is an optional layer of **role-specialized agents** that sit on AgentGlass / Foundry / timeline. They use **Quicksilver** (same provider family as ClutchBot A2A: DeepSeek + Gemini slots) for **phrasing and reasoning only**.

They are **not** ClutchBot, **not** a Twitch poster, and **not** a capture owner.

## Enable

```powershell
$env:QORESENCE_AGENT_SOCIETY = "1"
$env:QORESENCE_AGENT_SOCIETY_ROLES = "spam_warden,pilot_auditor"
# optional: same key file style as A2A / Quicksilver
python -m qoresence.cli --play --deck --agent-glass --agent-society
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
| ClutchBot | Live Twitch acts (fast/confirm) |
| A2A | Sparse scene↔chat negotiate under policy |
| Agent Society | Ops agents: warden, auditor, coach, editor |
| AgentGlass/MCP | Tool socket for external IDEs/agents |

## Quicksilver

Uses the same provider configuration style as A2A (`QORESENCE_QUICKSILVER_*` / `.secrets`). Models default to the project’s DeepSeek (reason) and Gemini-lite (scene) IDs — not Nvidia.
