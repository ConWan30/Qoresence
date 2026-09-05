# ClutchBot chat default → muse-spark-1.3

**BUILT.** Empty-shell ticket replaced. Do not merge until GO MERGE in Qorector chat.

## What landed

ClutchBot **chat** default on Quicksilver Pro is now `muse-spark-1.3`. Confirm / scoreboard VLM default is `gemini-3.5-flash-lite`. DualSense stays on the PS5.

| Surface | Change |
|---------|--------|
| `qoresence/agents/llm_client.py` | `DEFAULT_MODEL = "muse-spark-1.3"`. `DEFAULT_VISION_MODEL = "gemini-3.5-flash-lite"`. `DEFAULT_BASE_URL` remains `https://api.quicksilverpro.io/v1`. Module docstring/comments updated. |
| `qoresence/core/unified_config.py` | ClutchBot `llm_model` default and `QORESENCE_CLUTCHBOT_LLM_MODEL` fallback string → `muse-spark-1.3`. MatchAgent chat copy updated. |
| `qoresence/cli.py` | MatchAgent help + init log name `muse-spark-1.3`. |
| `qoresence/agents/match_agent.py` | Module/class docstring + start log name `muse-spark-1.3`. |
| `qoresence/a2a/deepseek_agent.py` | Docstring reuses ClutchBot chat slug `muse-spark-1.3`. |
| `README.md` + `docs/A2A_CLUTCHBOT.md` | Chat-default mentions → `muse-spark-1.3`. Scoreboard VLM pin not rewritten. |
| `tests/test_match_agent.py` | Asserts `DEFAULT_MODEL` / chat default `muse-spark-1.3`. Env overrides still win. |
| `tests/test_scoreboard_vlm.py` / `tests/test_confirm_ticket.py` | Vision≠chat compares against `muse-spark-1.3` / `DEFAULT_MODEL`. |

## Overrides (unchanged)

- `QORESENCE_CLUTCHBOT_LLM_MODEL` still wins for ClutchBot chat.
- `QORESENCE_MATCH_AGENT_MODEL` still wins for MatchAgent (`from_quicksilver_env`), then `QORESENCE_CLUTCHBOT_LLM_MODEL`, then `DEFAULT_MODEL`.
- `QORESENCE_SCOREBOARD_VLM_MODEL` still wins for confirm VLM.

## Out of scope

- Confirm / scoreboard VLM remains `gemini-3.8-flash`.
- DualSense stays on the PS5.
- No Spout. No #145. No Gemini Direct. No key changes.
- Do not merge this branch until GO MERGE.
