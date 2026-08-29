# Vendored fonts (Aperture Glass)

Self-hosted `woff2` so the Deck never depends on a runtime Google Fonts
stylesheet that can blank the glass offline. Files are `@font-face`-linked
from `src/styles.css` and bundled into `/assets/*.woff2` by Vite (served by
the Deck `/assets` static mount alongside the SPA JS/CSS).

| Family         | Weights (latin, normal) | Role                                   |
| -------------- | ----------------------- | -------------------------------------- |
| Instrument Sans | 400 / 500 / 600        | Chrome, nav, labels, titles            |
| IBM Plex Mono   | 500 / 600              | Licensed digits, empty glyphs, SYNC ms |

Both families are licensed under the SIL Open Font License 1.1 (OFL-1.1).

- Instrument Sans — Copyright The Instrument Sans Project Authors
  (https://github.com/google/fonts/tree/main/ofl/instrumentsans)
- IBM Plex Mono — Copyright IBM Corp. (https://github.com/IBM/plex)

`woff2` binaries were taken from the Fontsource distributions
(`@fontsource/instrument-sans`, `@fontsource/ibm-plex-mono`), latin subset.
Do not hand-edit the binaries; re-vendor from the same source if updating.
