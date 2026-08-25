# Contributing to Qoresence

Thank you for helping make Qoresence a local-first operations console for gamers and streamers. This guide covers setup, conventions, and how to open issues and pull requests.

## Quick setup

```powershell
git clone https://github.com/ConWan30/Qoresence.git
cd Qoresence
pip install -e ".[monitor]"        # or "[mcp]" for AgentGlass/MCP work
python scripts/pilot_preflight.py   # checks environment
```

## Running tests

```powershell
# Full suite
python -m pytest tests -q

# Core invariants you must not break
python -m pytest tests/test_deadlock_regression.py tests/test_security_localhost.py tests/test_agent_glass.py tests/test_mcp.py -v
```

## Project conventions

### One physical DShow device → one owner
The capture card is the brain. Never open the same physical device twice. See `docs/CAPTURE_OWNERSHIP.md`.

### Every lobe is OFF by default
New lobes start `enabled=False` and must be opt-in via CLI flag or config.

### Localhost by default
- Deck binds to `127.0.0.1`.
- AgentGlass / MCP connect to `127.0.0.1:8765`.
- `0.0.0.0` is rejected in tests. See `tests/test_security_localhost.py`.

### Deadlock invariants (AGENTS.md R1-R4)
- R1: Never emit an event while holding a re-entrant `RLock`.
- R2: Use a TLS re-entrancy guard before any recursive fanout.
- R3: Presence / fusion fanout happens outside the `RLock`.
- R4: Slow glasses (AgentGlass, MCP, leftover Twitch, Streamr) cannot block streamer, watchdog, or IVC.

If `health.video.age_s` climbs, assume a lock-ordering bug before blaming the card.

### No secrets in git
- Tokens live in `.secrets/` (gitignored).
- Client IDs and tokens are never committed.
- Do not post screenshots containing OAuth tokens.

## How to contribute

### Reporting bugs
Open an issue and include:
- Command you ran.
- Capture card model and whether OBS had it open.
- `http://127.0.0.1:8765/health` output.
- Relevant log lines from `logs/`.
- Whether the issue reproduces without `--a2a` / `--clutchbot`.

### Suggesting features
Open a discussion or issue and describe:
- Which plane it touches (Capture, Situation, Deck, AgentGlass, Social, Research).
- Whether it requires a new lobe or a new glass.
- Why the existing glasses cannot do it.

### Pull requests
1. Branch from `main`.
2. Add or update tests for deadlock/security invariants.
3. Update `docs/` and `docs/wiki/` if the feature is user-facing. Session Theater / CIVIF narrative changes go in `docs/SESSION_THEATER.md` and `docs/CIVIF.md`.
4. Keep commits focused on "why," not just "what."
5. Ensure `python -m pytest tests/test_deadlock_regression.py tests/test_security_localhost.py` passes.

### Style
- Python 3.11+.
- `ruff`/`mypy` are run in CI; fix warnings.
- Prefer compact code; do not add comments unless the behavior is non-obvious.

## Questions?

- Wiki: https://github.com/ConWan30/Qoresence/wiki
- Discussions: https://github.com/ConWan30/Qoresence/discussions
