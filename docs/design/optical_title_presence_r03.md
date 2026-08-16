# Optical Title-Presence · r03 Mitigation Realization Plan

**After r02 HOLD clearance.** Insertion map only — I2 implements the vertical slice.  
Ceremony is **deployed** onto `qoresence-research` only (operator grant required). Research ingredients are a live sidecar + ceremony path; optical records stay unmutated. Title-presence is **on with `--play`**.

## Wiring discovered (I1, live tree)

| Question | Finding | Tag |
|---|---|---|
| How constructed? | `QoresenceRuntime.init_lobes`: `if game_detection.enabled and visual.enabled` → `GameAutoDetector(...)` in `qoresence/cli.py` | deployed-verified |
| `--play`? | Does **not** set `game_detection.enabled`. Visual+outcome+streamer only. | deployed-verified (F2) |
| Enable flags | `--game-detect` / `--stream` on; `--no-game-detect` off; `QORESENCE_GAME_DETECT_ENABLED` | deployed-verified |
| Frame provider | `connect_lobes`: `streamer.get_current_frame` else `screen.get_current_frame` | deployed-verified |
| FrameHub | `qoresence/monitor/frame_hub.py` `get_latest` — subscriber, no DShow | deployed-verified |
| `game_detected` consumers | `SituationModel._handle_game_detected`, `OutcomeRuntime._on_game_detected`, ClutchBot/moment_scorer | deployed-verified |
| Enums | `EventType.GAME_DETECTED`, `SourceLobe.FUSION` in `qoresence/core/types.py` | deployed-verified |
| Stability | `_consecutive_detections` / `_stability_count` (default 2), emit at equality | deployed-verified |
| Default OFF pattern | All lobe `enabled: bool = False` in `unified_config.py` | deployed-verified |

## Mitigations → insertion

| Mitigation | Target | I2 action |
|---|---|---|
| 1. Local adaptation | Existing `learning_enabled` + `game_detection_learning.jsonl` | **DEFER** new loop. Do not expand. |
| 2. Event-driven sampling | `_run_loop` sleep; `poll_interval_s` | Thin: `lock_verify` window shortens sleep after menu→gameplay. Default stays sparse. |
| 3. Structural plane + bus | `core/types.py` + `_emit_game_detected` | New `TITLE_PRESENCE`; wrap `GAME_DETECTED` payload with `plane` + nested record **only when feature ON**. |
| 4. Research ingredients | — | **DEFER** (r02 C11). |
| 5. Hysteresis FSM | wrap `_maybe_emit_and_switch` | Pure FSM in `qoresence/vision/title_presence.py`; overlay via `VisualContext.game_state` (+ `effective_game_state` huddle). |

**Profile switch:** unchanged callback, still only fires when `game_detected` emits (now gated by `locked` if feature ON).

**Frame:** when feature ON, provider tries FrameHub `get_latest` then streamer buffer. Never a second capture.

**CLI:** `--title-presence` / `GameDetectionConfig.title_presence=False`. Not implied by `--play` or `--stream`.
