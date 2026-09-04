# X Live Studio — audience live (OBS owns RTMP)

Qoresence is the **local observatory**. X is the **public glass**. Live pixels stay in **OBS**. Qoresence never opens a second capture path and never becomes an X encoder.

Two surfaces, one clock:

| Surface | Owner | What it is |
|---------|--------|------------|
| Observatory | Qoresence | USB3.0 Video + DualSense + tickets + Foundry clips |
| Pattern B pixels | OBS Browser Source | `http://127.0.0.1:8765/obs-live.html` (Deck HDMI glass; brand when dark) |
| On-stream HUD | OBS Browser Source | `http://127.0.0.1:8765/overlay.html` (Clutch Lens, on top) |
| Audience live to X | OBS Custom RTMP | X Live Studio source (RTMP / RTMPS) |
| Timeline VOD | *not implemented* | Future opt-in X Glass lobe. This doc does not ship it |

Twitch is not a product route. Leftover Twitch clients stay default-OFF.

---

## Ownership rule

**One physical DirectShow device has one owner.** Recommended: **Qoresence** holds `USB3.0 Video`. OBS must **not** add a Video Capture Device for the same card.

This X Live recipe assumes **Pattern B**. Pattern A (OBS owns the card) is a different path — do not mix it with this RTMP recipe.

Full split: [OBS_OWNS_CARD.md](OBS_OWNS_CARD.md) · [tools/obs/README.md](../tools/obs/README.md)

---

## Live to X (Pattern B)

1. Start Qoresence on the **physical** card. Deck health `ok`. DualSense stays on the PS5. Observation plane only.
2. In OBS scene **LIVE**, stack two Browser Sources (1920×1080). Do **not** use `file:///`, raw `/video`, or a Video Capture Device on `USB3.0 Video`:
   | Layer | URL | Role |
   |-------|-----|------|
   | **Pixels (bottom)** | `http://127.0.0.1:8765/obs-live.html` | Deck HDMI glass. Embeds `/video?fps=30` with `object-fit: cover` (full-bleed for X; brand only when dark). Paints **QORESENCE / HDMI PORT · USB3.0 VIDEO · PATTERN B** only when the feed is dark so X is not letterboxed under a permanent slate. |
   | **Lens (top)** | `http://127.0.0.1:8765/overlay.html` | Clutch Lens HUD. Digits serialize only with ConfirmTicket + `score_vlm_locked` **and** a fresh ticket (`crop_hash` match, Same-Seq / clock age). Else empty glyphs / silence. `board_locked` alone is not a confirm. |
3. Open [X Live Studio](https://x.com/i/live-studio) (also `https://studio.x.com/live`). Create a **Source**. Copy the **RTMP URL** and **stream key**. Treat the stream key as a password.
4. OBS → Settings → Stream → **Custom** / Custom Streaming Server. Paste the Live Studio URL + key. Do not paste them into Qoresence, chat, git, or `.env` files that get committed.
5. Encoder (from X Live Studio help, 2026-09-03):
   - Video: **H.264**, recommended **1920×1080 @ 60**, ~**12 Mbps** (max 3840×2160 @ 60 / 40 Mbps)
   - Audio: **AAC 128 kbps**
   - **Keyframe interval: every 3 seconds** (72/90/150/180 frames at 24/30/50/60 fps). Official Live Studio help mentions OBS only for this keyframe note.
6. Pattern B pixels are **only** the `obs-live.html` Browser Source — **not** raw `http://127.0.0.1:8765/video?fps=60` (CEF often stays black), **not** `file://`, and **not** a second open of `USB3.0 Video` / dshow. Optional Display/Game Capture of a TV is fine when it is not the card Qoresence owns.
7. Clear OBS Safe Mode before `--startstreaming` (Safe Mode after a crash blocks RTMP). Helper: `tools/obs/pattern_b_x_live.ps1`. Then start streaming in OBS. Creating the livestream in Live Studio does **not** auto-post. Click **Post livestream on X** when you want it public.
8. One livestream per RTMP source. Max **24 hours**. A timed-out stream cannot be restarted; create a new source. Protected accounts cannot go live. No `--x-glass`. No stream keys in git.

### Verify before Post livestream

- `/health`: `video.age_s` low, `frames` climbing
- OBS: no Video Capture Device on `USB3.0 Video`
- Pixels Browser Source URL is `/obs-live.html` (brand visible when feed is dark)
- Overlay: unlocked board shows empty glyphs, not invented digits
- Then click **Post livestream on X**

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

Digits on any public glass serialize only with ConfirmTicket + `score_vlm_locked` **and** a fresh ticket (`crop_hash` match, Same-Seq / clock age). Else blank beats hold. `scoreboard_locked` / `board_locked` / `widgetsOk` are not digit permission. Shared gate: `glass/src/lib/coupling/board.ts` `pickBoard` — the overlay.html paint path consumes that ingest; do not darken the lens alone. This recipe does not invent scores.
