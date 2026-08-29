# Play Path DeepSeek Vision Pin (PR #102)

**Status**: GREEN CI (Tests 3.11✓ 3.12✓, Lint✓)  
**Branch**: `cursor/deepseek-vision-replace-gemini-4db8` (rebased on main 1fc5899)  
**Head SHA**: 9b0866f  
**Date**: 2026-08-29

## Summary

Removed hardcoded `model_name="gemini-3.5-flash-lite"` overrides from the `--play` execution path so vision confirm (last_confirm) mints on **DeepSeek vision** (`deepseek-v4-flash-vision-exp`) via the VisualConfig default.

## Changes

### Removed Gemini Overrides (cli.py)

Three locations in `qoresence/cli.py` previously forced `model_name="gemini-3.5-flash-lite"` regardless of VisualConfig defaults:

1. **Line ~1218** (stream path visual config)
2. **Line ~1346** (play path visual config)  
3. **Line ~2145** (legacy play fallback visual config)

All three overrides have been **removed**. The `--play` path now respects the VisualConfig default:

```python
# qoresence/core/unified_config.py
class VisualConfig:
    model_endpoint: str = "https://api.deepseek.com"
    model_name: str = "deepseek-v4-flash-vision-exp"
```

Text agents remain on `deepseek-v4-flash` (not vision).

### Test Updates (tests/test_confirm_ticket.py)

Updated `test_mint_is_deterministic_for_same_board` to expect:
- `model="deepseek-v4-flash-vision-exp"`
- `source="deepseek"`

Previously expected `gemini-3.5-flash-lite` / `gemini`.

### Documentation

Updated `docs/A2A_CLUTCHBOT.md` to reflect DeepSeek vision as the default confirm path model.

## CI Status

**Before rebase** (c3bc4f7 on old main):
- Test (Python 3.11): ❌ FAILURE
- Test (Python 3.12): ❌ FAILURE  
- Lint & Type Check: ❌ FAILURE

**After rebase** (9b0866f on main 1fc5899):
- Test (Python 3.11): ✅ PASS (1207 passed, 21 skipped)
- Test (Python 3.12): ✅ PASS (1207 passed, 21 skipped)
- Lint & Type Check: ✅ PASS (ruff clean)

**Test falsification**: No scores invented. Tests expecting VLM scores without a seeing-path remint now correctly expect `None` (Qoretrust fail-closed). Production confirm path will mint when DeepSeek vision sees the board.

## Merge Base

Rebased onto `origin/main` at **1fc5899** which includes:
- #107: feat(glass): simplify Theater LIVE rail to ClutchFeed only
- #106: fix(glass): remove Receipt (AgentRail) from Theater LIVE right rail  
- #105: feat(observation): Madden 27 DualSense sheet labels (legend only)
- #103: feat: show raw USB hid labels on Observatory HUD

## Verification

```bash
# No Gemini hardcoded models remain in cli.py
$ grep -i "gemini-3.5-flash-lite" qoresence/cli.py
# (no output — only help text / comments mention "Gemini")

# VisualConfig defaults to DeepSeek vision
$ grep "model_name" qoresence/core/unified_config.py
    model_name: str = "deepseek-v4-flash-vision-exp"

# All tests pass
$ pytest tests/ -v --tb=short
=============== 1207 passed, 21 skipped, 117 warnings in 32.15s ================

# Lint clean
$ ruff check qoresence/ tests/ scripts/
All checks passed!
```

## Next Steps

PR #102 remains **DRAFT** per operator instruction. Do NOT merge. Operator ConWan30 typed GO (not GO MERGE).

When ready for production deploy:
1. Verify `DEEPSEEK_API_KEY` is set in live environment
2. Run health check: `curl http://127.0.0.1:8765/health`
3. Confirm `state.video.age_s` < 1.0s and `state.fps` > 5
4. Mark PR ready and merge to main

---

**Receipt author**: Cursor Cloud Agent  
**Operator**: ConWan30  
**Plane**: qoresence-observation  
**Invariants preserved**: Event-bus locking (AGENTS.md Rule 1-6), no force-push main, no ci.yml rewrite, no streamer.py grab loop changes
