# Qoreeval Hygiene Fixes

**Date**: 2026-08-29
**Branch**: cursor/qoreeval-hygiene-fixes-9ca4
**PR**: #113 (OPEN — do not merge until operator types GO MERGE)

## Summary

Three observation-plane hygiene fixes for Receipt 1.1 residuals. DualSense stays
on the PS5. No Qoremem, overlay, or HUD verbs.

1. **Confirm remint**: reuse `ticket_id` when scores + teams are unchanged, on
   the same book the extractor `put()`s. Fill `session_id` from SessionAuthority.
2. **Garbage board**: refuse 0-0 after identity swap (not every 0-0), refuse
   82-86-class first locks, refuse live ticker identity swap (9-47 DAL-DET over
   IND-DET). Loading/cutscene marks identity stale and cannot mint.
3. **OBSERVE bodied**: `input_bodied` ignores laptop USB DualSense Edge
   (`hid_domain=observe`). `controller_bodied` is false unless PLAY events or
   `imu_bodied`. IVC `allow_bodied` stays fail-closed.

## Receipt 1.1 mapping

| Residual | What failed | What this PR does |
|---|---|---|
| Remint | 85 remints while session+lock+teams+score unchanged; `session_id=""` | `mint_confirm_ticket(book=)` reuses id from the book `put()` updates. Quarter flicker does not remint. Empty session_id → SessionAuthority.current() |
| Garbage | DAL 27–NO 0 → loading → IND 82–DET 86 → IND 0–DET 0 locked ~8 min | 82-86 is a suspicious pair. 0-0 after a different matchup is refused. Kickoff 0-0 of a new session is allowed. Loading cannot mint and stales identity so a later IND 3–DET 31 can lock |
| Bodied vs OBSERVE | `controller_bodied=true` on 72 ticks with Edge USB; `imu_bodied` never | Events with `hid_domain=observe` return `(False, "hid_observe")`. CIVIF ticks wipe `input_ticks` |

## What the first pass on this branch got wrong

- Remint tests constructed a local `ConfirmTicketBook` while `mint_confirm_ticket`
  read the process global — reuse never ran on the book the test put into.
- `_looks_suspicious_pair((0,0))=True` refused real kickoff 0-0.
- `_looks_suspicious_pair((82,86))` stayed False; tests asserted that.
- `locked_ok` started False and was never set True, so the VLM mint path minted
  nothing.
- OBSERVE was gated only on `imu_bodied`. InputRing Edge events still bodied.

## Operator notes

- Do not merge until GO MERGE
- #111 stays closed HOLD
- Next soak only after this lands on main and the operator plays **one**
  session without a bounce
