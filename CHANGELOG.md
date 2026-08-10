# Changelog

All notable changes to Qoresence. This project is pre-1.0 and under active pilot development.

## [Unreleased]

### Added
- **AgentGlass / Glass D** — read-only spectator API on `127.0.0.1:8765` with `snapshot`, `events`, `health`, `frame`, `clip`, and WebSocket `stream` endpoints.
- **MCP universal glass** — `qoresence-mcp` exposes 6 tools over stdio/SSE for any Cursor/Claude agent.
- `docs/wiki/` mirrored to GitHub Wiki with `_Sidebar.md`.
- `CONTRIBUTING.md`, `SECURITY.md`, `PRIVACY.md`, `CODE_OF_CONDUCT.md`, issue templates, and PR template.

### Changed
- Updated `docs/index.html` and `README.md` for AgentGlass / MCP.
- README milestones now include deadlock hardening, Streamr (experimental), VLM score lock, clip export, A2A sparsity, blank-frame guard, soak loggers, Twitch ClutchBot, and MCP glass.

## [Pilot Pass — 2026-08]

### Added
- Capture health runbook with 640x480/30fps fallback and VLM score merge invariants.
- Clip Foundry smoke test: MP4 + chapter sidecar.
- A2A soak logger and health soak logger for long validation sessions.
- `scripts/twitch_irc_test.py` for quick IRC token checks.

### Fixed
- A2A / presence live-deadlock that looked like a frozen capture card.
- Scoreboard extractor no longer invents fields on blank/uniform frames.
- Blank-frame guard prevents false score reads.
- Streamer timeout read and default 30fps restored.

### Changed
- A2A ambient triggers (`scene_tick`, `video_ambient`) now require pressure, coupling, or high-climax must-fire.

## [Pilot Pass — 2026-07]

### Added
- Streamr integration (experimental, default OFF) for publishing events to a local Streamr node.
- Twitch ClutchBot smoke test: IRC token → chat.
- Retina Deck LIVE with async MJPEG.

### Fixed
- DualSense Edge enumeration (`0x0DF2`) and clip export 5-tuple fix.
- FrameHub + Retina Monitor: no second capture open.

## Earlier

See `git log --oneline` for the full history before the 2026-07 pilot pass.
