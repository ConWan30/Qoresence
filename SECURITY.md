# Security Policy

## Supported versions

Only the latest `main` branch is supported with security fixes. Qoresence is pre-1.0 and fast-moving.

## Reporting a vulnerability

Please open a **private** GitHub advisory at:

https://github.com/ConWan30/Qoresence/security/advisories/new

Do **not** open a public issue for security bugs.

We aim to respond within 7 days and ship a fix within 14 days for verified high-severity issues.

## What Qoresence does to protect you

- **Local by default:** capture frames, clips, and logs stay on the local machine.
- **No `0.0.0.0` bind:** Deck, AgentGlass, and MCP default to `127.0.0.1`.
- **Tokens in `.secrets/`:** all tokens are gitignored. Never commit them.
- **Optional modules OFF:** leftover Twitch IRC/Helix, Quicksilver VLM/A2A, and Streamr are opt-in. Twitch is not a product route.
- **No anti-cheat / legitimacy claims:** the project produces observation evidence, not proof.

## Security practices for users

- Keep `.secrets/*.txt` and `.secrets/*.key` files out of screenshots and version control.
- Rotate leftover Twitch tokens if they ever appear in a commit or public log.
- Do not set `QORESENCE_DECK_HOST=0.0.0.0` on untrusted networks.
- Only enable `--agent-glass-require-token` if you are exposing the API beyond localhost (e.g., via Tailscale).

## Out of scope

- Anti-cheat circumvention.
- Bypassing game console DRM or terms of service.
- Cloud VLM prompt injection (report to the model provider).
