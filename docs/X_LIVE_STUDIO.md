# X Live Studio — audience live (OBS owns RTMP)

Qoresence is the **local observatory**. X is the **public glass**. Live pixels stay in **OBS**. Qoresence never opens a second capture path and never becomes an X encoder.

Two surfaces, one clock:

| Surface | Owner | What it is |
|---------|--------|------------|
| Observatory | Qoresence | USB3.0 Video + DualSense + tickets + Foundry clips |
| On-stream HUD | OBS Browser Source | `http://127.0.0.1:8765/overlay.html` (Clutch Lens) |
| Audience live to X | OBS Custom RTMP | X Live Studio source (RTMP / RTMPS) |
| Timeline VOD | *not implemented* | Future opt-in X Glass lobe. This doc does not ship it |

Twitch is not a product route. Leftover Twitch clients stay default-OFF.

---

## Ownership rule

**One physical DirectShow device has one owner.** Recommended: **Qoresence** holds `USB3.0 Video`. OBS must **not** add a Video Capture Device for the same card.

Full split: [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md) · [tools/obs/README.md](../tools/obs/README.md)

---

## Live to X (Pattern B)

1. Start Qoresence on the **physical** card. Deck health `ok`.
2. In OBS: **Browser Source** → `http://127.0.0.1:8765/overlay.html` (1920×1080). Do **not** use `file:///`.
3. Open [X Live Studio](https://x.com/i/live-studio) (also `https://studio.x.com/live`). Create a **Source**. Copy the **RTMP URL** and **stream key**. Treat the stream key as a password.
4. OBS → Settings → Stream → **Custom** / Custom Streaming Server. Paste the Live Studio URL + key. Do not paste them into Qoresence, chat, git, or `.env` files that get committed.
5. Encoder (from X Live Studio help, 2026-09-03):
   - Video: **H.264**, recommended **1920×1080 @ 60**, ~**12 Mbps** (max 3840×2160 @ 60 / 40 Mbps)
   - Audio: **AAC 128 kbps**
   - **Keyframe interval: every 3 seconds** (72/90/150/180 frames at 24/30/50/60 fps). Official Live Studio help mentions OBS only for this keyframe note.
6. Scene video is **Game / Display / Window Capture** of the play path — **not** the capture card Qoresence already owns.
7. Start streaming in OBS. Creating the livestream in Live Studio does **not** auto-post. Click **Post livestream on X** when you want it public.
8. One livestream per RTMP source. Max **24 hours**. A timed-out stream cannot be restarted; create a new source. Protected accounts cannot go live.

Simulcast: you cannot reuse a YouTube/Twitch stream directly. X names Restream / Castr for splitting one encoder output.

WHIP is **not** offered in Live Studio help. Do not add a Qoresence ingest path, Broadcasts API client, or second `VideoCapture`.

---

## Access notes

- Mobile in-app **Live** is a phone-camera path, not this recipe.
- Live Studio help does **not** clearly require Premium. Press has claimed a Premium gate. Check Live Studio access on the posting account rather than assuming a tier.
- Media Studio (the older producer) is documented as Premium / Premium+, not Basic.

---

## What this is not

- Not a Qoresence RTMP lobe
- Not a dual-open of `USB3.0 Video`
- Not a live path into QorTroller / PoAC / `*-truth`
- Not timeline clip posting (no OAuth, no `tweet_video`, no `--x-glass` in this change)
- Not anti-cheat, humanity, or eligibility claims. Language stays co-occurrence / coupling / presence evidence
- Not a Madden / EA safe harbor. X may drop sources on copyright enforcement. Observation of your own play session is not blessed by X text; a rights holder can still DMCA

Digits on any public glass still require confirm / `board_locked`. This recipe does not invent scores.
