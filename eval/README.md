# QoresenceScoreboard Bench

Starter dataset `scoreboard_bench.json` (20 samples) — expand to 10k via `logs/learning_samples.jsonl`.

## Run
```bash
python -m eval.harness --dataset eval/scoreboard_bench.json --model mock
python -m eval.harness --dataset eval/scoreboard_bench.json --model local
python eval/fusion_bench.py
python eval/wp_bench.py
```

## Metrics
- game_category accuracy, game_title accuracy, football score exact-match F1
- latency p50/p95 (target local <100ms)
- Fusion coupling AUROC, WP swing table

## Expanding
Capture frames with `VisionStack`, hash with sha256(gray), store expected `VisualContext` JSON.
Contributions require `frame_hash` stable.
