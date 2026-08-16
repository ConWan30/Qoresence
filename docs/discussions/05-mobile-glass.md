---
title: "Mobile Glass — same FrameHub on your phone"
category: Announcements
---

# Mobile Glass is on main

One aperture, another glass. `/mobile.html` plays the LIVE session from **FrameHub** (WebRTC first, MJPEG if `aiortc` is missing). The phone does not capture.

- **Local:** `http://127.0.0.1:8765/mobile.html` while `--play --deck` is running
- **Phone (same Wi‑Fi):** restart with `--deck-bind 0.0.0.0`, then scan the QR on Theater
- The PC **cannot** find nearby phones or open Safari/Chrome for you
- Title-presence is on with `--play` so the strip can show a locked title/score — or `—` when unknown

Docs: https://github.com/ConWan30/Qoresence/blob/main/docs/MOBILE_GLASS.md  
Pages: https://conwan30.github.io/Qoresence/#glasses
