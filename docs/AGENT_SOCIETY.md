# Agent Society — leftover opt-in stub (not the product path)

Qoresence is a **local-first ops console**. The product path is **actuators, not coworkers**:

| Actuator | Job |
|----------|-----|
| **Aperture** | HDMI / video health (`age_s`, frames) |
| **Bind** | DualSense ↔ HDMI join (PLL, lag, binds) — *not* a Society Sync Warden |
| **License** | Coupling ticket (heat) and confirm ticket + `score_vlm_locked` (digits) |
| **Arm** | Clip / stem *suggest* only when licensed |

Agent Society is a **leftover package**. Default OFF. `--play` does **not** turn it on. Personality roles (`drive_coach`, `ghost_editor`, `prediction_steward`, `spam_warden`, `pilot_auditor`) and the duplicate `sync_warden` role are **deleted**. `--agent-society` still opts in a **rules-only / no-op stub** so leftover imports do not crash.

They are **not** ClutchBot, **not** a Twitch poster, and **not** a capture owner. Do not promote Streamr, Twitch, or DePIN as the product route.

Cursor / Grok **operator bots** (Qorector, Nine-Bot Society, Qorefront, Qoreeval and the other specialists) are documented in [GROK_BOT_CORPS.md](GROK_BOT_CORPS.md). That charter is not this leftover package and must not reintroduce personality roles.

## Enable (opt-in leftover)

```powershell
python -m qoresence.cli --play --deck --controller --streamer-device 0 --streamer-fps 30
# Society stays off

python -m qoresence.cli --play --deck --agent-society
# opt-in stub: no personality ticks
```

Or set env:

```powershell
$env:QORESENCE_AGENT_SOCIETY = "1"
```

`--society-audit` / `--society-propose-cuts` are leftover one-shots and print nothing.

## Invariants

1. Default OFF
2. No DShow/HDMI open
3. No score digits unless `score_vlm_locked` and a confirm ticket
4. No direct Twitch API from society package
5. Background only — never block grabber/IVC
6. Observation-plane language only
7. Actuators are clock-licensed receipts — not Society coworkers

## vs A2A vs ClutchBot vs actuators

| Layer | Purpose |
|-------|---------|
| Aperture / Bind / License / Arm | Product path: health, sync, tickets, clip gate |
| ClutchBot | Live Deck / clutch-feed acts (fast/confirm) |
| A2A | Sparse scene↔chat negotiate under policy |
| Agent Society | Leftover opt-in stub — not the product path |
| AgentGlass/MCP | Tool socket for external IDEs/agents |
