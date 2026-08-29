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
- `feat/madden-control-labels` isolation HEAD: `4aee77068fc3bcdb787cacbd75180ef3686902e0`

## Addendum — CI-GATE-2 (2026-08-29)

Next `-x` stopper after isolation: `tests/test_civif_invariants.py::test_civif_live_and_highlights_run_inline_not_threadpooled`

`create_app()` returns `None` when FastAPI is missing. CI installs FastAPI *after* the main pytest job (`pip install fastapi httpx` in Glass SPA land hygiene). The test now reads `/api/civif/live` from `qoresence/deck/server.py` source, same as `test_civif_disk_routes_stay_threadpooled`. Product routes unchanged.

Lint: `qoresence.core` now exports `CFB_27_PROFILE` and `profile_from_title`. Isolation W293 stripped. Remaining pre-existing ruff on other files still being landed. No `ci.yml` change. No glass paint. No merge.

## CI

- `pytest -x` remains enabled in `.github/workflows/ci.yml`
- Test `test_coupling_min_uses_sidecar` now passes
- CIVIF live route test no longer requires FastAPI at pytest time
