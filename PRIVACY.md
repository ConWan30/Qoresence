# Privacy & Data Policy

Qoresence is **local-first** by design.

## What stays on your machine

- HDMI video frames from the capture card.
- Clip ring and exported `clips/*.mp4` files.
- Controller input events and `logs/`.
- Situation model, coupling scores, and event bus history.

None of these leave the machine unless you explicitly enable a glass that sends them out.

## What can leave your machine (opt-in)

| Feature | Data sent | How to enable |
|---------|-----------|---------------|
| Leftover Twitch IRC | Chat messages | leftover `--clutchbot-channel` + token (not the local route) |
| Leftover Twitch Helix clips | Clip URL to chat | leftover `--clutchbot-enable-clips` + `clips:edit` (prefer local Foundry MP4) |
| Quicksilver VLM | Scoreboard crop + metadata | `QORESENCE_QUICKSILVER_*` |
| A2A bus | Scene description + prompt | `--a2a` |
| Streamr | Selected events | `qoresence/streamr/`, experimental and default OFF |

## What we do **not** do

- Continuous 60 fps upload to the cloud.
- Store biometrics or controller fingerprints.
- Make humanity, legitimacy, or anti-cheat claims.
- Train models on your data unless you explicitly export `clips/` for that purpose.

## Best practices

- Keep `.secrets/` gitignored and never share token files.
- Delete `clips/` and `logs/` between sessions if you do not want local residue.
- Use `127.0.0.1` for Deck/AgentGlass on shared machines; enable token auth if you tunnel.

## Questions

Open a Discussion or email through the security contact in `SECURITY.md`.
