# ClutchBot chat + VLM defaults (Quicksilver)

**BUILT.** DualSense stays on the PS5.

## Pins

| Knob | Default |
|------|---------|
| ClutchBot / MatchAgent **chat** `DEFAULT_MODEL` | `muse-spark-1.3` |
| Scoreboard / confirm **VLM** `DEFAULT_VISION_MODEL` | `gemini-3.5-flash-lite` |
| Base URL | `https://api.quicksilverpro.io/v1` |

Same clutchbot key. Not Gemini Direct. Env overrides still win:
`QORESENCE_CLUTCHBOT_LLM_MODEL`, `QORESENCE_MATCH_AGENT_MODEL`, `QORESENCE_SCOREBOARD_VLM_MODEL`.

## Surfaces

`llm_client.py`, `unified_config.py`, `cli.py`, `match_agent.py`, `scoreboard_vlm.py` docs, README / A2A copy, and matching tests.
