# A2A ClutchBot — Gemini scene ↔ DeepSeek chat

Optional **agent-to-agent** bus that enhances ClutchBot chat under **local policy**.

Does **not** replace LocalVLM, scoreboard OCR, fast path, or DriveGraph. OCR remains the score referee.

---

## Agents (via Quicksilver Pro)

| Agent | Role | Model (default) | Endpoint |
|-------|------|-----------------|----------|
| **Gemini** (scene) | Sparse scene / tension (soft language) | `gemini-3.5-flash-lite` | `https://api.quicksilverpro.io/v1` |
| **DeepSeek** (chat) | Rewrite → Twitch-ready line | `deepseek-v4-flash` | same |
| **Policy** (local) | Veto invented scores; cooldown | — | in-process |

Cloud **VLM** (when not `prefer_local`) also defaults to Quicksilver **gemini-3.5-flash-lite** instead of NVIDIA Nemotron. `--play` still prefers **LocalVLM + OCR**.

---

## Enable

```powershell
# Secrets (never commit)
# put key in .secrets/quicksilver_clutchbot.key

$env:QORESENCE_A2A = "1"                 # master switch (or --a2a)
$env:QORESENCE_A2A_GEMINI = "1"           # live Gemini (else stub)
$env:QORESENCE_A2A_DEEPSEEK = "1"         # live DeepSeek (else stub)
# optional model overrides:
# $env:QORESENCE_A2A_GEMINI_MODEL = "gemini-3.5-flash-lite"
# $env:QORESENCE_A2A_DEEPSEEK_MODEL = "deepseek-v4-flash"

python -m qoresence.cli --play --deck --controller --a2a --streamer-device 0 --streamer-fps 60
```

Without API keys, **stubs** still run a full scene→chat→policy cycle (offline tests pass).

---

## Flow

```text
DriveGraph phase ∈ {pressure,armed,open} OR coupling high
        │  (background thread — never on capture loop)
        ▼
 GeminiSceneAgent.propose_scene  (+ optional JPEG)
        ▼
 DeepSeekChatAgent.propose_chat
        ▼
 A2APolicy.evaluate
   soft: no score digits
   confirm: digits must match OCR situation
        ▼
 CommitAct → ClutchBot deck_feed / chat backends
 SessionTimeline: a2a_scene | a2a_veto | a2a_commit
```

Triggers are **sparse** (~20s min interval). Not every frame.

---

## Policy rules

| Path | Rule |
|------|------|
| `fast` / soft | **No** scorelines like `21-17`; no inventing multi-digit board numbers |
| `confirm` | Scoreline digits must match local `home_score`/`away_score` |
| Always | Cooldown + no duplicate text |

---

## Health

`GET /health` may include:

```json
"a2a": { "enabled": true, "gemini_live": false, "deepseek_live": true, "recent_commits": [...] }
```

---

## Files

| Path | Role |
|------|------|
| `qoresence/a2a/types.py` | Messages |
| `qoresence/a2a/bus.py` | In-process bus |
| `qoresence/a2a/policy.py` | Veto / commit |
| `qoresence/a2a/gemini_agent.py` | Scene (stub/live) |
| `qoresence/a2a/deepseek_agent.py` | Chat (stub/live) |
| `qoresence/a2a/orchestrator.py` | Cycle + ClutchBot hook |
