# Qoresence Wiki

**Gaming Streaming Observatory Engine** — local-first, one clock, many glasses. HDMI/OBS frames + DualSense HID + situation model → Retina Deck, **Session Theater**, native monitor, Foundry clips, ClutchBot, and **AgentGlass / MCP** for any AI agent. The capture card is the brain; everything else is a glass.

**Actuators, not coworkers.** Aperture / Bind / License / Arm are clock-licensed receipts. Agent Society is leftover opt-in (`--agent-society`); `--play` does not enable it. Do not treat persona roles as the product path.

## Start here

| Page | Contents |
|------|----------|
| [What-is-Qoresence](What-is-Qoresence) | Mission, planes, non-goals |
| [Novel-Stack](Novel-Stack) | Architecture that differentiates the project |
| [Operator-Runbook](Operator-Runbook) | Daily Pattern B pilot (Qoresence owns card) |
| [Capture-Ownership](Capture-Ownership) | Qoresence owns card (recommended) vs legacy VCam |
| [Retina-Deck-and-Monitor](Retina-Deck-and-Monitor) | Glasses: Lens, Theater, LIVE, Mobile Glass, FrameHub monitor |
| [Session-Theater](Session-Theater) | Now + Story + Recap; live view/recap APIs; Open clip (shipped through `fef4d3c`) |
| [Mobile-Glass](Mobile-Glass) | Phone view of the same FrameHub session (WebRTC / MJPEG, QR on Theater) |
| [Native-Glass](Native-Glass) | Android cinema APK — `/live.jpg`, PiP, clutch HUD (view only) |
| [Title-Presence](Title-Presence) | Optical title lock; on with `--play`; observation plane only; profile pin persisted |
| [Retina-Monitor](Retina-Monitor) | Native OpenCV monitor window |
| [Controller-Video-Sync](Controller-Video-Sync) | InputRing + IVC |
| [Two-Speed-ClutchBot](Two-Speed-ClutchBot) | Fast video+input; OCR referee; local HUD digit lock (fail-closed) |
| [A2A-ClutchBot](A2A-ClutchBot) | Gemini↔DeepSeek chat agent; 25s cooldown, env-tunable |
| [Agent-Glass](Agent-Glass) | **Spectator API: HTTP/WS** |
| [MCP-Glass](MCP-Glass) | **MCP adapter for Cursor/Claude** |
| [Retina-Stem](Retina-Stem) | Situation-directed program; not OBS |
| [Streamr](Streamr) | Experimental DePIN publishing |

## Repo links

- [README](https://github.com/ConWan30/Qoresence#readme)
- [Session Theater (repo)](https://github.com/ConWan30/Qoresence/blob/main/docs/SESSION_THEATER.md)
- [Source docs/](https://github.com/ConWan30/Qoresence/tree/main/docs)
- [GitHub Pages](https://conwan30.github.io/Qoresence/)
- [Discussions](https://github.com/ConWan30/Qoresence/discussions)

Wiki source is also mirrored under `docs/wiki/` in the main repository so it survives wiki disable/re-enable.
