# Deck hygiene: SPA smoke + heavy-module size gate

Placeholder for implement PR. Shell-only until Grok / implement lands.

## Intent
1. Keep shipping the Retina Deck glass SPA the #25 way (`glass_spa` / vendored dist), never rely on gitignored `glass/dist` alone for live `:8765`.
2. HTTP smoke CI: load `/` (and Deck routes as needed), assert `#root` and `/assets/*.js` 200 for Theater / Lens / Foundry / Mobile.
3. Heavy-module size/shape gate: fail CI if known-heavy modules (`clutchbot.py`, `moment_scorer.py`, …) drop below a min byte count or collapse to a docstring stub (#23 class failure).

## Out of scope (this shell)
Feature code, lint quarantine implementation, shell-only label bot. Those ride in the implement PR or follow-ups.
