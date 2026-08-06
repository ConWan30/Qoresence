# Qoresence Roadmap

This roadmap reflects the **ClutchBot MVP**: a local game-state capture pipeline
with a Twitch agent. Optional research modules (fusion, trio-retina, on-chain
validation) are noted but not on the critical path.

## Phase 0 — Skeleton ✓
- [x] Folder structure
- [x] Git init + remote
- [x] README, LICENSE, pyproject.toml, .gitignore
- [x] docs/ARCHITECTURE.md, docs/clutchbot_setup.md
- [x] Initial commit

## Phase 1 — Core Capture Bus ✓
- [x] `qoresence/core/unified_config.py` — `RetinaUnifiedConfig` + lobe configs
- [x] `qoresence/core/types.py` — `SourceLobe`, `EventType`, `BaseEvent`
- [x] `qoresence/core/session.py` — `SessionAuthority.mint()`
- [x] `qoresence/core/event_bus.py` — `RetinaEventBus` with JSONL + WebSocket
- [x] Unit tests

## Phase 2 — Capture Lobes ✓
- [x] `qoresence/lobes/outcome.py` — game-specific event profiles
  - NCAA Football 27: score_changed, turnover, first_down, possession_changed
  - Call of Duty: kill, death, assist, streak
- [x] `qoresence/lobes/visual.py` — VLM-driven `visual_context`
- [x] `qoresence/lobes/screen.py` — screen capture + OCR/motion (optional)
- [x] `qoresence/lobes/controller.py` — HID capture (optional)
- [x] `qoresence/lobes/streamer.py` — UVC/OBS capture (optional)

## Phase 3 — ClutchBot MVP ✓
- [x] `qoresence/agents/situation_model.py` — rolling game state
- [x] `qoresence/agents/moment_scorer.py` — clutch-moment rules
- [x] `qoresence/agents/action_executor.py` — pluggable backends
- [x] `qoresence/agents/twitch_client.py` — IRC chat + chat commands
- [x] `qoresence/agents/helix_client.py` — clips + predictions
- [x] `qoresence/agents/eventsub_client.py` — follow/sub/redemption alerts
- [x] `qoresence/agents/clutchbot.py` — agent runtime + `agent_action` events
- [x] `qoresence/agents/session_memory.py` — JSONL audit trail
- [x] `tools/obs/presence_overlay.html` — OBS overlay
- [x] `tools/twitch-extension/panel.html` — viewer panel
- [x] `docs/clutchbot_setup.md` — setup guide
- [x] CLI + `integration_test.py` wiring
- [x] `tests/test_clutchbot.py`

## Phase 4 — Packaging & Polish
- [ ] `scripts/run_qoresence.py` or `qoresence` background entry point
- [ ] `--stream` preset that enables outcome, visual, clutchbot, and WebSocket
- [ ] System tray / status indicator (optional)
- [ ] Windows installer / one-liner launcher

## Phase 5 — Game Profile Expansion
- [ ] Additional football event types (sack, interception, two-point conversion)
- [ ] First-person shooter support beyond Call of Duty
- [ ] Community game-profile SDK

## Future Considerations (Optional / Research)

- **Fusion / Presence Engine**: cross-modal `PresenceReport` (currently off by default)
- **Trio-Retina**: w3bstream WASM validation and optional on-chain receipts
- **Data Availability**: PDA / Merkle-root receipts
- **Mobile Companion**: session monitoring app
- **V.A.P.I. / QorTroller Integration**: opt-in adapter for research use

## Versioning

| Version | Milestone |
|---------|-----------|
| 0.1.0   | Core bus + config |
| 0.2.0   | Outcome + Visual lobes |
| 0.3.0   | ClutchBot MVP |
| 0.4.0   | Packaging + `--stream` preset |
| 0.5.0   | Game profile expansion |
| 1.0.0   | Stable ClutchBot release |
