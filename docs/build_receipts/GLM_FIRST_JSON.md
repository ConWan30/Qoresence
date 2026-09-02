# GLM first JSON object (PR #150)

**Task**: Extract the first JSON object from chatty glm-5.3-flash scoreboard replies so `last_confirm` can lock.

**Status**: Landed on `feat/glm-first-json` PR #150 (`b223721`).

**Sources**:
- `qoresence/vision/scoreboard_vlm.py` — `first_json_object`, `_parse_json`, `_choice_text`
- `tests/test_scoreboard_vlm.py` — parse + choice_text contract tests

**Next**: Qoretrust P2

**Do not assume**:
- `finish=length` still HOLD (truncated reply, no parse)
- No model slug fallback
