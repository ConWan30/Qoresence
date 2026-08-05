# Qoresence Roadmap

## Phase 0 — Skeleton ✓
- [x] Folder structure
- [x] Git init + remote
- [x] README, LICENSE, pyproject.toml, .gitignore
- [x] docs/DEVIN.md, docs/ARCHITECTURE.md
- [x] Initial commit

## Phase 1 — Unified Config (Current)
- [ ] `qoresence/core/unified_config.py`
  - [ ] `RetinaUnifiedConfig` dataclass
  - [ ] `OutcomeConfig` + `GameProfile`
  - [ ] NCAA Football 27 profile (snap, down_advanced, first_down, score_changed, playclock_reset, quarter_changed, possession_changed)
  - [ ] Call of Duty profile (kill, death, assist, streak)
  - [ ] All lobe enable flags default `False`
  - [ ] `session_id`, `session_head_ns`, `device_id_hex`
  - [ ] Fusion weights
  - [ ] `eye_check_required: bool = True`
  - [ ] `never_claim_humanity: bool = True`
  - [ ] `validate()` method
- [ ] Unit tests (`tests/test_unified_config.py`)
  - [ ] All lobes default OFF
  - [ ] Validation rejects missing `session_id`
  - [ ] Validation rejects non-positive `session_head_ns`
  - [ ] Profiles present and documented
- [ ] Update README + ARCHITECTURE.md

## Phase 2 — Session Authority + Event Bus
- [ ] `qoresence/core/types.py` — shared event types, `SourceLobe` enum
- [ ] `qoresence/core/session.py` — `SessionAuthority.mint()`
- [ ] `qoresence/core/event_bus.py` — `RetinaEventBus`
  - [ ] JSONL writer
  - [ ] WebSocket server (127.0.0.1:8765)
  - [ ] Enforces `session_id` + `clock_ns` + `source_lobe`
- [ ] Synthetic test: multi-lobe events with shared identity

## Phase 3 — Streamer Lobe (First User Value)
- [ ] `qoresence/lobes/streamer.py`
  - [ ] UVC/OBS Virtual Cam capture (OpenCV)
  - [ ] Eye-check gate (mandatory first frame)
  - [ ] `activity`, `frame_stats`, `zone` emission
  - [ ] Presence-sync via touch file
- [ ] `tools/obs/presence_overlay.html` — OBS Browser Source
- [ ] CLI integration in `scripts/run_qoresence.py`

## Phase 4 — Controller Lobe
- [ ] `qoresence/lobes/controller.py`
  - [ ] HID enumeration + capture (hidapi)
  - [ ] Controller events with `causal_parent_ns`
  - [ ] Rolling buffer for causal correlation

## Phase 5 — Outcome Lobe
- [ ] `qoresence/lobes/outcome.py`
  - [ ] Profile loader from `OutcomeConfig`
  - [ ] NCAA Football 27 event emission
  - [ ] Call of Duty event emission
  - [ ] Extensible profile registry

## Phase 6 — Presence Fusion Engine
- [ ] `qoresence/fusion/presence.py`
  - [ ] Consumes `RetinaEventBus`
  - [ ] Produces `PresenceReport`
  - [ ] Weighted verdict with configurable weights
  - [ ] Cross-lobe anomaly detection

## Phase 7 — Packaging + Optional Adapter
- [ ] `scripts/run_qoresence.py` — background entry point
- [ ] System tray / status indicator (minimal)
- [ ] `qoresence/adapters/qortroller.py` — optional adapter
  - [ ] Accepts pre-minted `session_id`
  - [ ] Accepts device identity
  - [ ] Accepts attested HID window
  - [ ] Zero QorTroller imports in core path

---

## Future Considerations

- **Visual Lobe**: VLM integration (NVIDIA Nemotron, local models)
- **Screen Lobe**: WGC/DXGI capture + cv_motion + OCR
- **Data Availability**: W3bstream / PDA receipts
- **Mobile Companion**: React Native / Tauri mobile app for session monitoring
- **Game Profile SDK**: Extensible profile system for community contributions

---

## Versioning

| Version | Milestone |
|---------|-----------|
| 0.1.0   | Phase 1 complete (config + tests) |
| 0.2.0   | Phase 2 complete (session + bus) |
| 0.3.0   | Phase 3 complete (streamer lobe) |
| 0.4.0   | Phase 4 complete (controller lobe) |
| 0.5.0   | Phase 5 complete (outcome lobe) |
| 0.6.0   | Phase 6 complete (fusion engine) |
| 1.0.0   | Phase 7 complete (packaging + adapter) |