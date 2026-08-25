# What is Qoresence?

Qoresence is a **Gaming Streaming Observatory Engine** — a local-first, opt-in instrument that binds HDMI video, DualSense HID, and game situation onto one monotonic clock, then hangs operator glasses off that clock. The capture card is the brain; everything else is a glass.

It is an **observation-plane** instrument: it records co-occurrence, coupling, and presence evidence. It does not score humanity, eligibility, or tournament-grade presence, and it has no live path into a truth plane.

## Proof points (shipped on `main`)

- **FrameHub** — one physical DShow owner; monitor, IVC, Deck, and Mobile Glass subscribe, never dual-open the card
- **One clock** — every event carries `session_id` + `clock_ns` + `source_lobe`; IVC stamps press and frame with the same nanoseconds
- **Glasses** — Retina Deck (Lens + Theater), Session Theater (`/session.html` Now + Story + Recap), Mobile Glass (WebRTC / MJPEG, QR on Theater), native Retina Monitor, Foundry Ghost Cut, AgentGlass + 12 MCP tools
- **Title-presence** — optical title lock with a hard `plane: qoresence-observation` tag; on with `--play`; menu/pause fail closed
- **Two-speed ClutchBot** — `path=fast` video+input soft acts; OCR/outcome is `path=confirm` referee (never invents scores on fast)
- **Foundry clips** — true capture-ring MP4 + `.chapters.json` + `.buttons.json` + `.coupling.json` sidecars; searchable later on Deck; Session Theater **Open clip** only for validated `hdmi_clip_*` stems in the same session
- **Session Theater** — fail-closed `normalize_pack`; live `GET /api/session/view` and `GET /api/session/recap`; overlay on hold until laptop evaluation
- **OpenTelemetry (optional)** — `--otel` exports causal bus traces and DualSense↔video coupling metrics to a local Collector, plus trace-annotated clip sidecars; re-entrancy smoke alarm for the A2A/Presence deadlock class
- **MCP witness pack** — `get_observation` licenses what an agent may say; `wrap_observation` is grant-gated onto `qoresence-research` only
- **Wrap deny list** — truth-plane dests (`*-truth`, QorTroller / PoAC) are denied; no on-chain by default
- **Deadlock hardening** — re-entrancy guard in A2A + presence; locking invariants in `AGENTS.md`; regression tests in `tests/test_deadlock_regression.py`

## Planes

| Plane | Question it answers |
|-------|---------------------|
| Capture | What frames / buttons / OCR just happened? |
| Situation | What is the game state *now*? |
| Operator glass | Can I *see* and *act* locally without cloud? |
| Clutch (local) | Should Deck feed / local HDMI clips fire? |
| Stem | Which program should glasses show? (conductor on `--play`; not OBS) |
| Observation/OTel | Causal bus traces + coupling metrics? (--otel, off) |
| Research | Fusion / trio-retina validation? (optional, off) |

## Explicit non-goals

- Claiming humanity or “you are a real gamer” as a product feature
- Anti-cheat or legitimacy verification
- A live path into QorTroller / PoAC / `*-truth` (truth-plane dests are denied)
- Dual-opening the same physical DirectShow device as OBS
- Rebuilding OBS (scenes, RTMP, Virtual Cam, Browser Source host)
- Using Twitch stream delay as the sync master clock
- Requiring blockchain / on-chain for the MVP

## Principles

1. **All lobes default OFF** — operator enables deliberately
2. **One physical card → one owner** (recommended: Qoresence)
3. **Shared monotonic clock** joins modalities
4. **Co-occurrence language** for input↔video (`coupling`), not “proof”
5. **The capture card is the brain; everything else is a glass**

## Who it is for

- Streamers running NCAA Football / CoD-class titles with HDMI + OBS
- Operators who want local Foundry clips with button sidecars
- Researchers exploring presence / causal multi-lobe stacks without truth-plane claims
