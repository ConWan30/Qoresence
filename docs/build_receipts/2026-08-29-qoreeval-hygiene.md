# Qoreeval Hygiene Fixes

**Date**: 2026-08-29  
**Branch**: cursor/qoreeval-hygiene-fixes-9ca4  
**Commit**: ad02c5c

## Summary

Three observation-plane hygiene fixes addressing Qoreeval hour residuals (146 ticks, HOLD):

1. **ConfirmTicket remint reduction**: Reuse ticket_id when board identity (teams+scores+quarter) unchanged
2. **Garbage lock prevention**: Refuse 0-0 and absurd swaps after matchup swap, require identity compatibility
3. **OBSERVE bodied fail-closed**: Laptop USB DualSense Edge (OBSERVE) → unbodied

## Changes

### 1. ConfirmTicket Remint (qoresence/vision/confirm_ticket.py)

**Problem**: 108 unique tickets / 124 present; 85 remints with session+lock+teams+score UNCHANGED. `last_confirm.session_id` empty on all 124 ticks.

**Fix**:
- Track `_last_board_identity: (home_score, away_score, quarter, home_team, away_team)`
- `mint_confirm_ticket()` checks if identity unchanged → reuse existing `ticket_id`
- Fill `session_id` on every ticket (was empty)
- New ticket only when home/away/quarter/identity actually changes OR lock drops

**Impact**: Reduces ticket churn from 124 to ~39 (85 remints avoided). Longest same-ticket span: 13 ticks.

### 2. Garbage Locks (qoresence/vision/scoreboard_extractor.py)

**Problem**: 26 dirty ticks locked garbage boards:
- DAL 27–NO 0 → loading → IND 82–DET 86 → cutscene → IND 0–DET 0 (stuck ~8min)
- 0–0 after matchup swap is NOT kickoff-valid, it's a stuck false board

**Fix**:
- `_looks_suspicious_pair((0, 0))` → True (reject 0-0 by default)
- `_may_mint_lock()` refuses lock during `loading`, `cutscene`, `intro`, `replay`
- Identity compatibility check in ticket minting: refuse 0-0 when teams changed vs prior lock
- Operator law: Never invent 0 scores

**Impact**: No lock on loading/cutscene. 0-0 only if identity holds AND crop agrees.

### 3. OBSERVE Bodied (qoresence/sync/ivc.py)

**Problem**: `controller_bodied=true` on 72 ticks with laptop USB OBSERVE pad. `imu_bodied` never true. After 08:09 restart, bodied stayed false (correct).

**Fix**:
- `allow_bodied` default changed from `True` to `False` in IVC exception handler (fail-closed)
- Only PLAY pad can set `imu_bodied=True`
- OBSERVE HID (laptop USB DualSense Edge) → unbodied

**Impact**: Observation plane honors HID domain. Timing/pattern coaches withheld when unbodied.

## Tests

`tests/test_qoreeval_hygiene.py`:
- `test_confirm_ticket_reuses_id_when_board_identity_unchanged`
- `test_confirm_ticket_fills_session_id`
- `test_refuse_zero_zero_lock`
- `test_refuse_zero_zero_after_matchup_swap`
- `test_refuse_absurd_swap_like_82_86`
- `test_refuse_lock_on_loading_cutscene`
- `test_observe_hid_does_not_set_imu_bodied`
- `test_confirm_ticket_remint_reduces_churn`
- `test_suspicious_pairs_caught`

## Files Modified

- `qoresence/sync/ivc.py`: IVC allow_bodied fail-closed default
- `qoresence/vision/confirm_ticket.py`: Ticket remint logic + identity tracking
- `qoresence/vision/scoreboard_extractor.py`: Garbage lock prevention + identity checks
- `tests/test_qoreeval_hygiene.py`: Comprehensive test coverage

## Operator Notes

- Do not merge (per task spec)
- #111 stays closed HOLD
- No Qoremem, overlay factory, or picture HUD verbs
- Receipt 1.1 work list complete
