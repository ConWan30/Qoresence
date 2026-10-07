# Pages fonts (Qoresence / Aperture Glass)

Self-hosted `woff2` so GitHub Pages never depends on a runtime font CDN or
Google Fonts stylesheet. Same binaries as `glass/src/fonts` (Retina Deck),
latin subset from the Fontsource distributions. `docs/aperture.css` is the
only file that declares `@font-face`, and it points only at these files.

| File | Family | Weight | Role |
| --- | --- | --- | --- |
| `instrument-sans-latin-400-normal.woff2` | Instrument Sans | 400 | Body |
| `instrument-sans-latin-500-normal.woff2` | Instrument Sans | 500 | Labels, nav |
| `instrument-sans-latin-600-normal.woff2` | Instrument Sans | 600 | Titles, buttons |
| `ibm-plex-mono-latin-500-normal.woff2` | IBM Plex Mono | 500 | Code, wire, HOLD speech |
| `ibm-plex-mono-latin-600-normal.woff2` | IBM Plex Mono | 600 | Kickers, status codes |

## Licenses

Both families are licensed under the SIL Open Font License 1.1 (OFL-1.1).
The full license texts ship next to the binaries:

- Instrument Sans — Copyright 2022 The Instrument Sans Project Authors —
  [`LICENSE-Instrument-Sans.txt`](./LICENSE-Instrument-Sans.txt)
- IBM Plex Mono — Copyright 2017 IBM Corp., Reserved Font Name "Plex" —
  [`LICENSE-IBM-Plex-Mono.txt`](./LICENSE-IBM-Plex-Mono.txt)

Do not hand-edit the binaries; re-copy from `glass/src/fonts` if updating.
Only weights 400/500/600 (sans) and 500/600 (mono) exist, so the stylesheet
never asks for 700/800 (no synthesized bold).
