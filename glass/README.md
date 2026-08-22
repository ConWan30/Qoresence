# Retina Deck glass (Grok Build)

Drop-in UI for Qoresence Deck URLs.

Same origins Qoresence already serves:
- /  and /deck.html  Retina Theater
- /overlay.html      Clutch Lens
- /studio.html       Foundry
- /mobile.html       Mobile glass

Python spine (--play --deck --a2a --agent-glass) is unchanged.
This is the frontend subscriber: HDMI JPEG, situation, VLM board lock,
ClutchBot/Quicksilver, Agent Society, HDMI clips.

## Land in Qoresence
Keep this tree under glass/ on branch glass/retina-deck.
Do not commit .secrets or QUICKSILVER_API_KEY.

## Run

```powershell
cd glass
npm install
npm run build
```

Deck serves packaged `qoresence/deck/glass_spa` at the same URLs (a stale
local `glass/dist` leftover must not win):

```powershell
.\qoresence.bat --play --deck --agent-glass --streamer-fps 30
```

- `http://127.0.0.1:8765/` and `/deck.html` — Theater
- `/overlay.html` — Clutch Lens (OBS)
- `/studio.html` — Foundry
- `/mobile.html` — Mobile glass

If `glass_spa` is missing, Python tries `glass/dist`, then `qoresence/deck/*.html`.

Dev (Vite on :5173, proxies APIs to Deck):

```powershell
npm run dev
```

Deck still owns the capture card on 127.0.0.1:8765. Do not commit `.secrets` or `QUICKSILVER_API_KEY`.
