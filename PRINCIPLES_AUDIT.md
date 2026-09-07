# Principles audit — `game-profile-pin-holds`

Loop: `docs/QORGRAPH_GAME_PROFILE.md`  
DShow verifier: `docs/QORGRAPH_DSHOW_VERIFIER.md`  
Date: 2026-09-07

## PIN — explicit operator pin is not yanked by optics

| Gate | Evidence | Result |
|---|---|---|
| `explicit_pin_not_yanked` | `SituationModel.seed_profile(..., pinned=True)` + `_maybe_apply_profile`; CLI `switch_profile` calls `operator_pin_blocks_switch`. Tests: `test_situation_pin_rejects_ncaa_claim`, `test_visual_context_does_not_yank_pin`, `test_optical_lock_observes_but_does_not_yank_pinned_profile`, `test_operator_pin_blocks_optical_switch`. | pass |
| CLI / env / last-file pin | `resolve_operator_profile`: CLI → `QORESENCE_GAME_PROFILE` → `last_game_profile` → unpinned `ncaa_football_27`. Tests: `test_resolve_cli_pins`, `test_resolve_env_pins`, `test_resolve_last_session_pins`, `test_first_run_ncaa_is_not_a_pin`. | pass |
| Unpinned fallback does not self-pin | `persist_operator_pin` writes `last_game_profile` only when `pinned=True`. CLI parse no longer `save_last_profile` on first-run NCAA. Tests: `test_unpinned_fallback_does_not_persist`, `test_pinned_persists_last_profile`. | pass (gap fixed) |
| `plane_tag_qoresence_observation` | `claim_record` / `no_claim_record` / `game_detected` payload `plane`. Tests: `test_plane_hard_on_claim_and_no_claim`, `test_title_presence_on_gates_and_tags_plane`. | pass |
| `claim_false_profile_id_null` | `no_claim_record` sets `profile_id=None`. Tests: `test_plane_hard_on_claim_and_no_claim`, `test_low_confidence_is_no_claim`, `test_overlay_rejects_claim`. | pass |
| `wrap_deny_list` | Default allowlist `qoresence-research` only; `dest_denied` for `qortroller` / `poac` / `*-truth`. Tests: `test_wrap_ceremony_fail_closed`, `test_research_ceremony_links_ingredient_without_mutating`. | pass |
| Menu / pause / overlay-rejected sleep scorebug | `docs/DARK_THEATER_SAME_SEQ.md`; `tests/test_live_paint.py` plane-dim. Title-presence overlay-rejected is no-claim. | pass (incumbent) |
| Community YAML / built-ins | `profiles/*.y*ml` via `load_community_profiles`; built-ins unchanged. Tests: `test_profile_sdk.py`, `test_cfb_27_profile.py`, `test_madden_profile.py`. | pass |

**Gap found:** CLI `save_last_profile(_gp)` ran on every parse, including unpinned NCAA fallback. The switch-callback last-file safety net then treated first-run as pinned, so optics could not lock the live title. Fix: `persist_operator_pin(..., pinned=)` and `operator_pin_blocks_switch`.

Locked optics still **observe**: `game_detected` emits with `plane: qoresence-observation` and nested `title_presence`. Observation must not call `outcome.set_game_profile` when a pin holds.

## DSHOW — one card, subscribe not own

| Gate | Evidence | Result |
|---|---|---|
| `one_card_owner` | `qoresence/capture/lease.py`; `tests/test_capture_lease.py`. | pass |
| `subscribe_not_own` | Title-presence `_get_frame` uses FrameHub `get_latest` first, then streamer buffer. No `VideoCapture` in detector / title-presence / operator pin / situation model. Tests: `test_title_presence_frames_from_framehub_first`, `test_title_presence_does_not_open_capture`. | pass |
| `lease_second_acquire_raises` | `test_second_acquire_raises` | pass |
| `pattern_b_dual_open_hard_fail` | `test_pattern_b_helper_hard_fails_dshow_dual_open` | pass |
| `obs_lens_browser_source_only` | unchanged; no new glass | pass |

This loop adds **zero** new DShow / `VideoCapture` opens.

## Must remain empty

No score digits on the observation record. No wrap dest containing `qortroller` / `poac` / `*-truth`. No dual-open capture.
