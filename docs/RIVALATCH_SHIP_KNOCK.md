# Rivalatch ship knock — Qoresence tip on the shared ship door

Rivalatch (VibeGate) lodges the **frozen** `gate.run` body for a Qoresence commit:

```json
{
  "app_ref": { "type": "git", "uri": "https://github.com/ConWan30/Qoresence", "rev": "<40-hex sha>" },
  "checks": ["smoke"],
  "acceptance": { "criteria": [], "base_url_path": "/" },
  "idempotency_key": "qoresence-<ship|glass>-<sha>"
}
```

The door shallow-clones this public repo at `rev`, serves `docs/` (the Pages
root) and smokes `GET /`. Same tip + same surface → **Recalled** (200), not a
second job. No new Spec fields, no fourth tool.

## Surfaces

| Surface | What | Key? |
|---------|------|------|
| Mobile Glass (`/mobile.html`, `/glass`) | "Knock Rivalatch · <sha7>" pill + Share → `rivalatch://knock?…` for the **local checkout tip** (`GET /api/rivalatch/knock-link`) | **No** key on the page |
| CLI | `python qoresence/deck/rivalatch_knock.py link` (deep-link) / `lodge --sha <sha>` (prints `job_id` + `verdict`) | `lodge` reads `VIBEGATE_API_KEY` from env; never printed |
| CI (separate, opt-in) | `.github/workflows/rivalatch-ship-receipt.yml` on push to `main` | repo secret `VIBEGATE_API_KEY`; absent → skip-closed |

## Honesty

- Tip unknown (not a git checkout) → pill shows **HOLD**, no link built.
- A local commit that is not pushed cannot be cloned → door answers `fail_class=infra`.
- The phone does not lodge by itself: the link is for a Rivalatch client
  (agent / MCP host / Shortcut) that holds the key.
