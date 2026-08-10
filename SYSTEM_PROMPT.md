# SYSTEM_PROMPT.md — Devin.AI Bootstrap for Qoresence

> **Copy-paste entrypoint:** Give Devin the `PROMPT` block below as its initial task. It is self-contained and runs Phases 1-6 sequentially.

---

## PROMPT — Paste this into Devin.AI

```
You are continuing Qoresence (ClutchBot) in the current cloned workspace, branch main.

## CONTEXT — READ FIRST
- Project: Qoresence = local capture -> situation -> stream pipeline (RetinaEventBus). Lobes in qoresence/lobes/ (streamer, screen, visual, controller, outcome, fusion), vision in qoresence/vision/, config single-source in qoresence/core/unified_config.py. Docs: docs/ROADMAP.md (Phases 0-4 done), docs/ARCHITECTURE.md.
- Capture safety: use only an explicitly allowlisted capture source. Webcam/person-frame protection and the mandatory operator eye-check must remain enabled. Never use a laptop webcam for gameplay capture, and never commit live capture artifacts.
- Privacy: runtime logs, clips, sessions, eye-check images, models, and secrets are gitignored. The only tracked images are intentionally curated public website screenshots under docs/assets. Never commit camera frames, room images, logs, or JSONL.
- Tech: Python 3.11 (uv), opencv DSHOW/MSMF, onnxruntime CPU, mediapipe, mss, pygrabber. A missing local model may use the documented local heuristic fallback. Tests: tests/test_local_vlm.py tests/test_visual_lobe.py.

## CONSTRAINTS
1. Sequential only — do not start Phase N+1 until Phase N passes its Acceptance Criteria + git commit + push.
2. Privacy guard must stay ON — no capture from a laptop webcam, no person frame allowed, eye-check REQUIRED for any live capture.
3. Never add logs/ or images to git. Verify with `git check-ignore -v` before any commit.
4. Windows paths but write OS-agnostic code where possible (CAP_DSHOW fallback to MSMF).

## PHASES — EXECUTE IN ORDER

### PHASE 1: Data Hygiene + Verification (do this first)
Tasks:
- Validate any local session JSONL used for evaluation; keep raw and derived artifacts outside Git.
- Confirm each line is valid JSON and contains the required event fields.
- Remove temporary local previews only when the operator approves; keep runtime artifacts gitignored.
- Run `git status -s` and `git check-ignore -v` before every commit.
Acceptance: validation passes, runtime artifacts remain outside Git, and the working tree contains no private capture data.

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
3. If Devin needs a new live capture, it must use an explicitly approved capture source, show you an eye-check image, and wait for you to confirm `FIELD` before continuing. Revoke if it tries to open a laptop webcam.
4. Expect one commit+push per phase. Review `git log --oneline`.

## Local artifacts (gitignored, never pushed)

- `logs/*.jsonl` — runtime event history
- `logs/eye_check_*.png` — operator-only capture checks
- `logs/capture.err` — local diagnostics
- `clips/` and `sessions/` — local session data

## Privacy guarantee (enforced)

Runtime logs, clips, sessions, eye-check images, model files, and secrets are ignored by Git. Verify with `git check-ignore -v` before committing. Only intentionally curated public website screenshots under `docs/assets/` may be tracked. The capture allowlist and person-frame guard must remain enabled; never disable them or commit live camera frames.
