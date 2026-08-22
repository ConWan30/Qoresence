# Deck hygiene: SPA smoke + heavy-module size gate

Guards what reaches `main` for Retina Deck glass shipping (PR implement track).

## (1) Vendored SPA + smoke

- Ship the Vite build under `qoresence/deck/glass_spa/` (preferred on `:8765`).
  A stale gitignored `glass/dist` must not win — it hid HDMI on livePaint flicker.
- Static land check: `python scripts/check_glass_spa.py`
  - `#root`, hashed `/assets/*` present, JS/CSS size bounds, ship markers
- HTTP smoke: `python scripts/smoke_deck_spa_http.py`
  - `GET /deck.html` `/overlay.html` `/studio.html` `/mobile.html` → 200 + `#root`
  - every referenced `/assets/*` → 200

Pytest: `tests/test_glass_spa_ship.py`, `tests/test_deck_spa_http_smoke.py`

## (2) Heavy-module size/shape gate

- `python scripts/check_heavy_modules.py`
- Fails if `clutchbot.py` / `moment_scorer.py` drop below min bytes, lose required
  AST classes, or collapse to a docstring stub (#23 class failure).

Pytest: `tests/test_heavy_modules.py`

## CI

Wired in `.github/workflows/ci.yml` and `.github/workflows/ci-hardening.yml`.

## Out of scope here

Lint/deck-smoke split and shell-only guard ride in follow-up hygiene steps.

Refresh vendored SPA: `python scripts/vendor_glass_spa.py` (copies glass/dist -> qoresence/deck/glass_spa).
