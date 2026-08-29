# CIVIF Index Test Isolation Receipt

**Plane**: qoresence-observation  
**Dest**: qortroller-truth denied  
**Date**: 2026-08-29

## Issue

**Test**: `tests/test_civif_index.py::test_coupling_min_uses_sidecar`

**Before**: Test failed with `assert 8 == 0`

The test wrote one clip with coupling=0.1 to `tmp_path`, then called:
```python
none = search_clips("", clips_dir=tmp_path, limit=8, coupling_min=0.5)
assert none["count"] == 0  # FAILED: assert 8 == 0
```

**Root Cause**: `qoresence/foundry/index.py::search_clips()` correctly filtered the test clip (coupling 0.1 < 0.5), but when `hits` was empty, it fell back to `get_session_timeline().recent(80)` and filled up to `limit=8` with foreign timeline events from the environment. This is not a Foundry product bug—it is test isolation leakage.

## Fix

Isolated the test by monkeypatching `qoresence.agents.session_timeline.get_session_timeline` to return a mock timeline with an empty `recent()` list. Also set `QORESENCE_CLIPS_DIR` env var to `tmp_path` as belt-and-suspenders isolation.

**After**: Test passes; timeline fallback returns `[]` in the test context.

## Files Touched

- `tests/test_civif_index.py` — added `monkeypatch` fixture parameter and two monkeypatch calls to `test_coupling_min_uses_sidecar`

## Production Code

**NO** changes to production code:
- `qoresence/foundry/index.py` — UNTOUCHED
- `glass/` — UNTOUCHED
- `.github/workflows/ci.yml` — UNTOUCHED

## Branch State

- `main` left at: `85e8fb2d421002ef80ec65b3a0d7dca0b3be7731`
- `feat/madden-control-labels` old HEAD: `f6adcc219aec4e96f5e35fb015030f2ff37a4a03`
- `feat/madden-control-labels` new HEAD: (to be determined after commit)

## Lint

Did NOT run `ruff --fix` repo-wide.  
Pre-existing W293/F401/F841 on seeing-path / session-recap / sheet-conflict remain HOLD.

## CI

- `pytest -x` remains enabled in `.github/workflows/ci.yml`
- Test `test_coupling_min_uses_sidecar` now passes
- CI gate for PR #105 can proceed

## Verification Steps

1. `pytest tests/test_civif_index.py::test_coupling_min_uses_sidecar -q` → PASS
2. `pytest tests/test_civif_index.py -q` → PASS
3. `pytest tests/test_madden_controls_observation.py tests/test_mcp.py -q` → PASS
4. `git diff` confirms no changes to `.github/workflows/ci.yml`, `qoresence/foundry/index.py`, or `glass/`
5. No secrets in diff
