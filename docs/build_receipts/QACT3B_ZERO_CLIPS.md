# Q-ACT-3b — 0 Recap `hdmi_clip_*` (session `qoresence_06b8c404882b`)

**Cause class: A — armed never.**

Evidence: `audits/session-recap-matchend-20260913T100822.json` (QorAct rig) · 22 confirmed `situation_shift` · `linked_clip_count: 0` · every event `bodied: false`. DualSense play was on the PS5; Recap HID empty.

## file:line

1. Confirm scorer **does** mint a clip moment on a real score delta: `qoresence/agents/moment_scorer.py:543-551` (`_should_auto_clip_score` + `action="clip"`, payload `{path: confirm, seconds: 30}`).
2. ClutchBot then **drops** that clip unless `arm_allowed`: `qoresence/agents/clutchbot.py:472-481`.
3. `arm_allowed` is true on `locked_score_delta` or `climax >= 0.65` or operator POST: `qoresence/agents/actuators.py:186-196`.
4. `SituationState.to_dict()` has **no** `score_changed` / `locked_score_delta` (`qoresence/agents/situation_model.py` — those keys are absent). Clip payload from (1) also omits them. Climax on the one exported sidecar was `0.2` (`clips/hdmi_clip_20260913_100300.chapters.json` graph_summary).
5. Fast-path clip never fires without coupling ≥ 0.55 and red/close-late: `qoresence/agents/fast_moment.py:118-119`. Coupling on the sidecar was `0.0` (`clips/hdmi_clip_20260913_100300.coupling.json`).
6. Recap only links `evidence.clip_ids` that already resolved to an on-disk stem: `qoresence/foundry/narrative_engine.py:157` stamps `t.get("clip_id")`; `qoresence/foundry/session_view.py:229-231` + `642-680` copy the view and **do not re-scan** `clips/` (`tests/test_session_recap.py:209`).

One MP4 **did** write at 10:03 (`clip_buffer.py` log `HDMI clip saved: clips\hdmi_clip_20260913_100300.mp4`) with matching `session_id`. Ticks never carried `clip_id`, so Recap stayed 0. That is linker-miss of an export, not 22 armed windows.

## This WP

- **Not D-CLIP:** do not auto-clip every `situation_shift`. Do not plumb `locked_score_delta` onto every score tick here.
- **Stop-flush:** `HdmiClipBuffer.note_arm` / `flush_armed` — write only if a clip already passed `arm_allowed` and the ring still has frames. Else honest `armed_no_file` / `not_armed`. `clip_id` is None unless a file exists.
- `LocalHdmiClipBackend.stop` calls `flush_armed_clips()` fail-open. JPEG pump is not joined.

D-CLIP remains HOLD: operator Cut vs auto-arm on situation_shift.
