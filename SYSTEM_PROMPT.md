# SYSTEM_PROMPT.md — Devin.AI Bootstrap for Qoresence

> **Copy-paste entrypoint:** Give Devin the `PROMPT` block below as its initial task. It is self-contained and runs Phases 1-6 sequentially.

---

## PROMPT — Paste this into Devin.AI

```
You are continuing Qoresence (ClutchBot) — repo at C:/Users/Contr/qoresence, branch main.

## CONTEXT — READ FIRST
- Project: Qoresence = local capture -> situation -> stream pipeline (RetinaEventBus). Lobes in qoresence/lobes/ (streamer, screen, visual, controller, outcome, fusion), vision in qoresence/vision/, config single-source in qoresence/core/unified_config.py. Docs: docs/ROADMAP.md (Phases 0-4 done), docs/ARCHITECTURE.md.
- Today 2026-08-06: Fixed capture source bug. Old path used mss screen grab on primary monitor -> dark frame mean 39 green 0.00 -> 6116 lines all visual_context=shooter. New path is direct UVC via qoresence/lobes/streamer.py StreamerRuntime on [0] 'USB3.0 Video' (HDMI capture card) with CAP_DSHOW 1280x720@30. OBS Virtual Camera is [2] fallback. [1] '720p HD Camera' is USER ROOM — BLOCKED by _is_allowed_capture_name() + _frame_contains_person() (MediaPipe >25% = BLOCK). Mandatory eye-check saves logs/eye_check_<ns>.png + logs `EYE-CHECK REQUIRED: Verify ... shows GAME, not webcam/black HDCP` — human must verify FIELD not room before continuing.
- Commits: 0b7e228 (cli --streamer-device/backend/width/height + heuristic green 0.18→0.06 edge 0.04→0.02) -> 5112e31 (never hallucinate SHOOTER in football: edge>0.06 green<0.08 now -> UNKNOWN 0.38 or MENU/dark luma<35, not SHOOTER 0.62). Pushed to origin/main.
- Session artifact 2026-08-06 15:37-15:49: PID 21492 --streamer --streamer-device 0 --streamer-backend dshow --game-profile ncaa_football_27 --visual --visual-prefer-local --visual-sample-rate 6. Eye-check eye_check_19405562000000.png 1.84MB green 0.39 person=False -> FOOTBALL (verified FIELD by user 15:41). JSONL logs/session_real_2026-08-06.jsonl 14038 lines (140% of 10k) 9.09MB visual total 4273 {shooter:2452 football:1821} last 500 {football:128 shooter:84} — but session is 100% NCAA Football 27, so 2452 shooter are FALSE (playcall/replay/zoom menu frames). CLEAN file exists as logs/session_2026-08-06_direct_usb0_CLEAN.jsonl (needs verification — see Phase 1). Stopped clean PID 21492 dead 15:49. Artifacts in logs/ are gitignored (.gitignore:29).
- Privacy: .gitignore:29 = logs/ + eye_check_*.png. git ls-files *.png/*.jpg = EMPTY, git log --all -- *.png = EMPTY. NEVER commit logs/, *.png, *.jpg, *.jsonl. 0 images ever pushed — keep it that way.
- Tech: Python 3.11 (uv), opencv DSHOW/MSMF, onnxruntime CPU, mediapipe, mss, pygrabber. Model tried models/qoresence-vlm-distilled.onnx (missing) -> fallback local:heuristic in qoresence/vision/local_vlm.py. Tests: tests/test_local_vlm.py tests/test_visual_lobe.py.

## CONSTRAINTS
1. Sequential only — do not start Phase N+1 until Phase N passes its Acceptance Criteria + git commit + push.
2. Privacy guard must stay ON — no capture from 720p HD Camera, no person frame allowed, eye-check REQUIRED for any live capture.
3. Never add logs/ or images to git. Verify with `git check-ignore -v` before any commit.
4. Windows paths but write OS-agnostic code where possible (CAP_DSHOW fallback to MSMF).

## PHASES — EXECUTE IN ORDER

### PHASE 1: Data Hygiene + Verification (do this first, 15 min)
Tasks:
- Verify logs/session_real_2026-08-06.jsonl (14038 lines) vs logs/session_2026-08-06_direct_usb0_CLEAN.jsonl. If CLEAN missing or still has shooter>0, recreate it: map every visual_context where game_category=="shooter" (case-insensitive) -> game_category="unknown", game_state gameplay->unknown, confidence 0.62->0.38, add _cleaned_from="shooter". Keep SRC untouched, DST is trainable set. Report BEFORE/AFTER counters.
- Validate JSONL: each line valid JSON, types present, visual_context has confidence/latency/model.
- Archive: delete temp previews logs/preflight_*.jpg logs/preflight_direct.jpg (keep 1 eye_check as proof if needed, but it's gitignored). Run `git status -s` — should be clean.
- Commit if you regenerated CLEAN: `chore(data): clean 2026-08-06 session 2452 shooter->unknown` (no logs in commit — this is docs only, file stays gitignored; just commit the _clean.py script removal or a README note if needed. If nothing to commit, just report).
Acceptance: python shows AFTER {football:~1821 unknown:~2452 shooter:0}, both files gitignored, working tree clean.

### PHASE 2: Visual Heuristic Hardening
File: qoresence/vision/local_vlm.py
Tasks:
- Add temporal hysteresis: 3-5 frame majority vote / EMA so single menu frame doesn't flip category. E.g., LocalVLMClient holds deque last 5 categories, emit smoothed category if 3/5 agree else UNKNOWN.
- Make profile-aware: add param game_profile to analyze_frame/heuristic; when profile==ncaa_football_27, disable SHOOTER emission entirely (already done for single-frame, now enforce for smoothed too).
- Add unit tests in tests/test_local_vlm.py: green 0.25 edge 0.27 -> FOOTBALL, edge 0.17 green 0.00 luma 39 -> UNKNOWN/MENU not SHOOTER, green 0.00 luma 16 -> MENU.
- Run pytest tests/test_local_vlm.py tests/test_visual_lobe.py -q green.
Acceptance: Tests pass, manual probe on logs/preflight_ready_best.jpg still FOOTBALL, menu frame -> UNKNOWN, no SHOOTER when profile=football.

### PHASE 3: Distill Real Local VLM (ONNX)
Tasks:
- Use CLEAN jsonl (14038 lines) as pseudo-labels: green>0.06+has_scoreboard=True -> FOOTBALL, else UNKNOWN/MENU. Or hand-label 20 frames from eye_verify.jpg + preflight images. Train tiny model (e.g., MobileNet/ResNet18) to 224x224, export to models/qoresence-vlm-distilled.onnx. Implement _onnx_infer to output logits [football, unknown, menu] -> VisualContext.
- Update LocalVLMClient._try_load to actually load and warmup, fallback to heuristic only if file missing.
- Benchmark: avg_ms <100ms CPU.
Acceptance: LocalVLMClient().get_stats().mode == "onnx" when model exists, analyze_frame on eye_verify.jpg -> FOOTBALL conf>0.6, menu frame -> UNKNOWN/MENU, p50 <100ms.

### PHASE 4: Football VisualContext Field Extraction
Files: qoresence/vision/visual_context.py, qoresence/lobes/visual.py, qoresence/lobes/outcome.py
Tasks:
- Populate VisualContext football fields (score, quarter, down, distance, clock, possession) via VLM prompt or OCR on scoreboard crop. Start with scoreboard detection (top bar) + simple OCR/regex. Wire through VLMClient.analyze_frame -> outcome lobe.
- Ensure to_dict/from_dict handles new fields without breaking shooter sessions.
Acceptance: On a live 10s direct capture (if user allows) or on saved eye_verify.jpg/preflight frames, VisualContext shows game_category=football + at least score/quarter populated, no shooter leakage.

### PHASE 5: Fusion + Streamer Hardening
Tasks:
- Fix `temporal_desync - Lobe streamer silent for 5.0s` (seen x2 in capture.err) — add cap.grab() retry, lower fps_target to 15 if USB saturates, or thread heartbeat.
- Add fusion smoothing for visual_context (reuse Phase 2 hysteresis in qoresence/fusion/presence.py).
- Add CLI helper `python -m qoresence.cli --streamer-list` to enumerate DShow devices via FilterGraph.get_input_devices().
Acceptance: 5-min direct capture shows 0 temporal_desync warnings, fusion emits stable game_category.

### PHASE 6: Eval + Replay
Tasks:
- Add eval script eval/eval_session.py that replays CLEAN jsonl through fusion/outcome and reports football precision (should be 100% after cleaning), latency histogram, desync count.
- Add CI check: pytest + eval on CLEAN must pass before push.
Acceptance: python eval/eval_session.py logs/session_2026-08-06_direct_usb0_CLEAN.jsonl -> football precision 1.0, avg VLM latency <100ms (or <50ms heuristic), 0 shooter found.

## DELIVERABLE PER PHASE
- Code + tests, git commit -m "phase N: ..." and git push origin main
- Short report: what changed, metrics, and git status -s + git log --oneline -3

Start with PHASE 1 now. Ask for human eye-check verification before any live capture. Do not proceed to Phase 2 until Phase 1 acceptance prints pass.
```

---

## How to run (operator checklist)

1. Open Devin.AI -> New Session -> paste entire `PROMPT` block above.
2. Devin will clone `origin/main` at `5112e31` and start Phase 1. It will **not** push images because `logs/` is gitignored — verify its first `git status -s` is clean.
3. If Devin needs a new live capture, it must: use `--streamer-device 0 --streamer-backend dshow`, show you `logs/eye_check_*.png`, and wait for you to confirm `FIELD` before continuing. Revoke if it tries `720p HD Camera`.
4. Expect one commit+push per phase. Review `git log --oneline`.

## Local artifacts (gitignored, never pushed)

- `logs/session_real_2026-08-06.jsonl` — 14038 lines RAW (polluted, keep for audit)
- `logs/session_2026-08-06_direct_usb0_CLEAN.jsonl` — same lines, shooter→unknown
- `logs/eye_check_19405562000000.png` / `logs/eye_verify.jpg` — field proof 15:41
- `logs/capture.err` — contains 2× `temporal_desync 5.0s` to fix in Phase 5

## Privacy guarantee (enforced)

`.gitignore:29` = `logs/` + `eye_check_*.png` + `*.db` + `sessions/` + `models/*.onnx` (check actual file). Verified: `git ls-files | grep -E '\.(png|jpg)$'` = empty, `git log --all --name-only | grep -E 'eye_check|preflight'` = empty. The user's room (`720p HD Camera` idx1) is blocked by `qoresence/lobes/streamer.py:_is_allowed_capture_name()` and `_frame_contains_person()` — Devin must not disable these.

— Generated 2026-08-06 16:07 from live session 15:37-15:49 direct USB3.0 Video prove-out.
