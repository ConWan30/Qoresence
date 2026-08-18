# A2A ClutchBot — Gemini scene ↔ DeepSeek chat

Optional **agent-to-agent** bus that enhances ClutchBot chat under **local policy**.

Does **not** replace LocalVLM, scoreboard OCR/VLM referee, fast path, or DriveGraph.  
**OCR + scoreboard Gemini referee** remain the score source of truth.

---

## Agents (via Quicksilver Pro)

| Agent | Role | Model (default) | Endpoint |
|-------|------|-----------------|----------|
| **Gemini** (scene + board) | See the frame, lock confirm, soft scene | `gemini-3.5-flash-lite` | `https://api.quicksilverpro.io/v1` |
| **Chat / reason** (A2A DeepSeek slot) | Rewrite → Twitch-ready line | `nemotron-3.5-lightning` | same |
| **Policy** (local) | Veto invented scores; cooldown; near-dupe | — | in-process |

**Scoreboard Gemini** (separate referee) runs at ~1.5s on gameplay (not 60 fps), faster on score/menu transitions. See `qoresence/vision/scoreboard_vlm.py`.

---

## Enable

```powershell
$env:QORESENCE_A2A = "1"
$env:QORESENCE_A2A_GEMINI = "1"
$env:QORESENCE_A2A_DEEPSEEK = "1"
# optional override (default is nemotron-3.5-lightning on Quicksilver Pro):
# $env:QORESENCE_A2A_DEEPSEEK_MODEL = "nemotron-3.5-lightning"
# $env:QORESENCE_CLUTCHBOT_LLM_MODEL = "nemotron-3.5-lightning"
# optional: $env:QORESENCE_SCOREBOARD_VLM_INTERVAL = "1.5"

python -m qoresence.cli --play --deck --monitor --streamer-fps 60 --a2a
```

---

## Triggers (reason codes)

| Reason | When | Typical interval |
|--------|------|------------------|
| `score_changed` | home/away pair changes | ≥ 8s |
| `menu_exit` | menu/hub → gameplay | ≥ 12s |
| `drive_pressure` | DriveGraph pressure/armed/open | ≥ 20s |
| `coupling` | IVC coupling high (pad) | ≥ 25s |
| `scene_tick` | gameplay ambient scene + JPEG | ≥ 45s |
| `video_ambient` | legacy rare fallback | ≥ 90s |

**No A2A on pure menu** (except `menu_exit` once you leave).

```text
reason fires
    │  background thread (never capture loop)
    ▼
 GeminiSceneAgent (+ optional JPEG)
    ▼
 DeepSeekChatAgent
    ▼
 A2APolicy (soft: no score digits; dupe/near-dupe; cooldown 45s)
    ▼
 CommitAct → DeckFeed only once
```

---

## Policy rules

| Path | Rule |
|------|------|
| `fast` / soft | **No** explicit scorelines (`X-Y`); bare numbers like "gained 12 yards" are allowed |
| `confirm` | Scoreline digits must match local `home_score`/`away_score` |
| Always | 25s chat cooldown (env: `QORESENCE_A2A_CHAT_COOLDOWN_S`); exact + near-duplicate veto 120s / 40-char prefix (env: `QORESENCE_A2A_DUPLICATE_WINDOW_S`) |

---

## Health

`GET /health` → `a2a`: `enabled`, `gemini_live`, `deepseek_live`, `last_reason`, `recent_commits`, `recent_vetos`.
