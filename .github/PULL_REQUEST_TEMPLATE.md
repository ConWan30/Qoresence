## Summary

<!-- Why this change? What does it improve? -->

## Plane affected

- [ ] Capture
- [ ] Situation
- [ ] Deck / Monitor
- [ ] AgentGlass / MCP
- [ ] Social
- [ ] Research
- [ ] Docs / repo health

## Test plan

- [ ] `python -m pytest tests/test_deadlock_regression.py tests/test_security_localhost.py tests/test_agent_glass.py tests/test_mcp.py -v` passes
- [ ] Full suite: `python -m pytest tests -q` (note environment-only failures)
- [ ] Updated `docs/` or `docs/wiki/` for user-facing changes
- [ ] No secrets or tokens committed
- [ ] No `0.0.0.0` bind added

## Checklist

- [ ] I have read `AGENTS.md` and `CONTRIBUTING.md`.
- [ ] Capture ownership invariants are respected.
- [ ] New lobes default to `enabled=False` if applicable.
- [ ] Slow glass fanout does not block streamer/watchdog/IVC.
