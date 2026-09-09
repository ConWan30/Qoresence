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

---

# Principles audit — `ivc-empty-hid-success`

Loop: `docs/QORGRAPH_IVC_EMPTY_HID.md`  
DShow verifier: `docs/QORGRAPH_DSHOW_VERIFIER.md`  
Date: 2026-09-07  
Branch: `qorgraph-2-ivc-empty-hid` @ `c47b784` + this commit

## Path B — empty laptop HID is success

| Gate | Evidence | Result |
|---|---|---|
| `empty_hid_is_success` | `ControllerRuntime.get_stats()` sets `reason=pad_not_on_this_host` when `connected=false`. `/health` snapshot copies that reason and keeps `ok: true`. CIVIF `build_coupled_tick` / sidecar `input.reason`. Tests: `test_start_without_device_waits`, `test_empty_hid_health_is_success_not_pad_wait`, `test_empty_pad_is_valid`, `test_live_tick_empty_hid_is_pad_not_on_this_host`. | pass (gap fixed) |
| `no_pad_wait_failure` | Fallback Lens `overlay.html` no longer paints a pad-wait chip. Fallback Deck `deck.html` copy is `DUALSENSE ON PS5` / `pad_not_on_this_host`, not a USB-plug failure. Glass SPA already used `pad_not_on_this_host`. Tests: `test_overlay_and_deck_do_not_say_pad_wait`. | pass (gap fixed) |
| `same_clock_ns_press_and_frame` | HID `InputEvent.clock_ns` + FrameHub `clock_ns` are the same monotonic domain; IVC payload `video_clock_ns` / `frame_seq` join the stamp. Test: `test_ivc_press_and_frame_share_clock_ns`. | pass |
| `no_heat_without_coupling_ticket` | `license_heat_text(heat, ticket=None) == ""`. `mint_coupling_ticket(..., pll_lock=False)` is `None`. Tests: `test_sprint_mints_and_licenses_heat`, `test_sprint_without_pll_does_not_mint`. | pass (incumbent) |
| `no_throw_phrase` | `THROW` not in `PHRASES` / `LIVE_PHRASES`; mint returns `None`. Test: `test_throw_phrase_does_not_mint`. | pass |
| `haptic_does_not_body_controller` | Haptic schema has no `controller_bodied`. Empty HID tick stays `pad_not_on_this_host`. Tests: `test_haptic_probe_does_not_body_empty_hid`, `test_unbodied_pulse_does_not_set_controller_bodied`. | pass |
| `one_card_owner` | IVC / Ghost Stick / InputRing / CIVIF / haptic probe do not construct `VideoCapture`. Lease second acquire still raises. Tests: `test_ivc_and_ghost_do_not_open_capture`, `test_second_acquire_raises`, `test_pattern_b_helper_hard_fails_dshow_dual_open`. | pass |

**Gap found:** Path B empty HID was already honest on CIVIF sidecars and the Glass SPA, but `/health` omitted `pad_not_on_this_host`, fallback Lens painted a pad-wait chip, and fallback Deck said `WAITING FOR DUALSENSE` (test_studio even locked that copy in). That is PAD WAIT as failure. Fix: stats/snapshot reason, hide the Lens pad chip unless this host has HID, Deck copy DualSense-on-PS5.

USB/BT on this host remains Path A lab (`ingest_report` / `feed_bodied_r2`). Heat speech still requires a live coupling ticket. Play-phrase lattice stays OFF (`classify_phrase` → `OFF`); tickets mint only from `LIVE_PHRASES` with `pll_lock` + fresh video.

## Clip sidecar reminder

`.coupling.json` stays keyed by `frame_seq` + `video_clock_ns` (`docs/CONTROLLER_VIDEO_SYNC.md`). Empty pad sidecars remain valid (`bodied=false`, `reason=pad_not_on_this_host`).

## Must remain empty

No PAD WAIT as failure. No invented 0-0. No THROW. No heat without a coupling ticket. No digits without a confirm ticket. No haptic bodying. No second DShow open.

---

# Principles audit — `theater-query-not-capture`

Loop: `docs/QORGRAPH_SESSION_THEATER.md`  
DShow verifier: `docs/QORGRAPH_DSHOW_VERIFIER.md`  
Date: 2026-09-07  
Branch: `qorgraph-4-theater`

## Recap is a query over the fail-closed pack

| Gate | Evidence | Result |
|---|---|---|
| `no_second_capture` | Theater/Recap/CIVIF files contain no `VideoCapture` / `getUserMedia`. Served `/session.html` and `/civif.html` are fallback query pages (`session.html` / `civif.html` not in `_GLASS_HTML_NAMES`). Recap is `recap_from_envelope(build_session_response(...))`. Tests: `test_theater_recap_civif_do_not_open_capture`, `test_session_and_civif_html_are_not_glass_spa`, `test_live_view_does_not_call_generate_narrative`. | pass |
| `no_new_clip_ids` | Stem remains `hdmi_clip_<token>`. Aliases (`hdmi_a`), paths, `%`, NUL, missing files, cross-session, int/empty sidecar session → `{available: false}`. Tests: `test_permitted_stem_rejects_paths_and_aliases`, `test_missing_file_and_cross_session_are_withheld`, `test_fixture_hdmi_aliases_do_not_leak`. | pass |
| `digits_need_confirm_and_vlm_lock` | `_live_board_licensed` requires `score_vlm_locked` and a non-empty `confirm_ticket_id`. Flag-only lock stays dark. Tests: `test_overlay_flag_only_is_dark_no_ticket`, `test_flag_only_lock_does_not_paint_digits`, `test_flag_only_http_sit_does_not_paint_pack_or_sit_digits`, `test_overlay_ticket_and_lock_paints_digits`. | pass |
| `missing_fields_empty_glyphs` | Unlicensed overlay writes `confirmed = {available: false, score: None, yard_line: None}` and does not stamp `board_why=confirm_ticket` from pack last-good. Tests: `test_unlicensed_live_clears_pack_last_good_digits`, `test_unlocked_strips_stuffed_score_and_yard`, `test_live_unlocked_does_not_leak_stuffed_score`. | pass (gap fixed) |
| `open_clip_existing_mp4_only` | `resolve_event_clip` requires existing `hdmi_clip_*.mp4` plus `.coupling.json` `session_id` string equal to the view session. Recap does not re-resolve. Tests: `test_linked_clip_when_file_and_session_match`, `test_recap_from_envelope_does_not_reresolve_clips`. | pass |
| `one_card_owner` | Lease second acquire still raises. Pattern B helper still `DUAL_OPEN`. No new DShow open in this loop. Tests: `test_second_acquire_raises`, `test_pattern_b_helper_hard_fails_dshow_dual_open`, `test_theater_recap_civif_do_not_open_capture`. | pass |

**Gap found:** Live Now HUD kept narrative-pack scores when the current sit was unlicensed (quota / flag-only / no ticket), then `build_session_response` stamped `board_why=confirm_ticket` because `confirmed.available` was still true. That is last-good overlay digits. Fix: `overlay_live_board` clears `confirmed` unless `score_vlm_locked` and a non-empty ConfirmTicket; do not infer confirm from pack last-good.

MCP `civif_narrative` / `civif_session_view` / `export_clip` stay off `tools/list`. `/civif.html` is not rewritten. Clip-dock stays off `/session.html`. One `tickAll` timer.

## Residual (not served)

Glass SPA `SessionNow` still calls `useTheaterLoop` (`ensureCapture`). `_GLASS_HTML_NAMES` does not include `session.html` or `civif.html`, so the operator glass is the fallback query pages. Do not add those names without removing the theater-loop grab from Session Now.

## Must remain empty

No second HDMI grab. No new clip IDs. No last-good overlay digits. No operator `confirm: none` on the Now HUD. No MCP `civif_*` session-view / export tools. No `/civif.html` rewrite.

---

# Principles audit — `a2a-reentrancy-default-off`

Loop: `docs/QORGRAPH_A2A_REENTRANCY.md`  
DShow verifier: `docs/QORGRAPH_DSHOW_VERIFIER.md`  
Date: 2026-09-07  
Branch: `qorgraph-5-a2a-reentrancy`

## A2A / Society stay default OFF

| Gate | Evidence | Result |
|---|---|---|
| `play_does_not_enable_a2a` | `--a2a` is `store_true`; `ClutchBotConfig.a2a_enabled` defaults False; `--play` wiring uses `args.a2a or config.clutchbot.a2a_enabled` only. `from_env` maps `QORESENCE_A2A` as explicit opt-in. Tests: `test_play_does_not_enable_a2a`, `test_clutchbot_a2a_default_off`, `test_from_env_a2a_opt_in`. | pass |
| `play_does_not_enable_society` | Existing `test_play_leaves_society_off`; Society config default `enabled=False`. | pass |
| `in_trigger_guard_present` | `A2AOrchestrator` keeps `self._tls.in_trigger`. Test: `test_in_trigger_guard_present`. | pass |
| `emit_outside_lock` | Deadlock suite: `test_suppressed_trigger_emits_outside_lock`, `test_presence_lock_released_during_report_fanout`. | pass |
| `deadlock_tests_not_deleted` | Required names still defined. Test: `test_deadlock_regression_tests_not_deleted`. | pass |
| `one_card_owner` | No new DShow open in this loop. | pass |
| `otel_enqueue_only` | Unchanged; OTel path not modified. | pass |

**Config honesty:** `RetinaUnifiedConfig.from_env` now sets `clutchbot.a2a_enabled` from `QORESENCE_A2A` so CLI `args.a2a or config.clutchbot.a2a_enabled` matches the env opt-in documented on `--a2a`.

`qoresence.bat` may still pass `--a2a` as a *launcher* default — that is not a Python `--play` default and is left alone.

## Must remain empty

No `--play` implies `--a2a`. No Society personality roles. No emit while holding lobe `_lock`. No Presence Fusion as product path. No dual-open. No scorelines on path=fast from A2A.

---

# Principles audit — `deck-lease-lamp-0.1`

Loop: `docs/QORGRAPH_DECK_LEASE_LAMP.md`  
DShow verifier: `docs/QORGRAPH_DSHOW_VERIFIER.md`  
Date: 2026-09-09  
Branch: `cursor/deck-lease-lamp-0.1-2ae5`

## DECK_LEASE_LAMP — Sight Glass is a glass on FrameHub

| Gate | Evidence | Result |
|---|---|---|
| `lamp_default_off` | `RetinaUnifiedConfig.deck_lease_lamp` defaults False; `lease_lamp.enabled()` False; `/health` omits `deck_lease_lamp` when off. Test: `test_deck_lease_lamp_default_off`. | pass |
| `play_does_not_enable_lease_lamp` | `--play` block in `qoresence/cli.py` does not latch `deck_lease_lamp`. `--play` help states the lamp stays OFF. Test: `test_play_does_not_enable_lease_lamp`. | pass |
| `plane_tag_on_every_emit` | Snapshot / `attach_health` / DOM `data-plane` are `qoresence-observation`. Test: `test_lamp_emits_plane_tag`. | pass |
| `dark_when_lease_not_ok` | `lease.ok` false or FrameHub subscribe missing → `lamp=dark`, `ok=false`. Never fakes ok. Test: `test_lamp_dark_when_lease_not_ok`. | pass |
| `no_digit_paint` | Lamp emit keys are lease/subscribe chrome only. Sources have no `home_score` / `0-0` / ConfirmTicket paint. Test: `test_lamp_source_has_no_digit_paint`. | pass |
| `one_card_owner` | Lamp / Deck chrome / `webrtc_hub` / `live_paint` do not construct `VideoCapture`. Lease second acquire still raises. Tests: `test_lamp_paths_do_not_open_capture`, `test_second_acquire_raises`. | pass |

**Gap found:** Sight Glass already subscribed to FrameHub (WebRTC / MJPEG / `get_latest`) and `/health.lease` already reported `{ok, owner, pid, device}`, but Deck had no opt-in chrome proving the glass leases held frames. Operators could read the feed as a second brain. Fix: default-OFF DeckLeaseLamp that paints lease + subscribe only, dark when the lease is not ok.

DualSense on PS5 stays observe language. This lamp does not invent scores from the pad or the board.

## Must remain empty

No DShow / `VideoCapture` open. No grab. No score digits / last-good / 0-0. No ConfirmTicket claims. No LocalScoreReferee / LocalMuse. No A2A default ON. No `wrap_observation` / `*-truth`. No FrameHub ownership steal. Eval HOLD: chrome only.
