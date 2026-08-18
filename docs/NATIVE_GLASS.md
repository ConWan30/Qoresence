# Native Glass — Android spectator cinema (Phase 2)

`Qoresence Glass` is a **view, never a capture owner**. Same FrameHub as
Theater / Monitor / IVC. The Android app is **not** a wrapped copy of the
iPhone PWA. Safari cannot do these things; the APK can:

1. **JPEG cinema pump** — Android WebView cannot play MJPEG. The app polls
   `/live.jpg` at ~5 fps from the same ClipBuffer as `/video`. Empty
   buffer returns 503 (no placeholder painted as LIVE). PiP keeps pumping.
2. **mDNS auto-pairing** — NSD scan for `_qoresence._tcp`. No IP typing.
3. **Clutch haptics + HUD** — heat bar + why-line + heavy haptic when
   `coupling.climax_score` crosses 0.4. Digits stay `—` until locked.
4. **Picture-in-picture** — Home / Pop-out keeps the live glass over chat
   or another app (16:9).
5. **Keep-awake** while live.
6. **Background clutch alerts** — foreground service polls `/api/situation`
   every 5 s (local notification, no cloud).
7. **Save clip** — `POST /api/clip` writes the HDMI ring to the **PC**
   `clips/` folder. The phone does not capture.

iPhone still uses Option A: Safari → Add to Home Screen. That path is
WebRTC / MJPEG. It does **not** get PiP, keep-awake, NSD, or clutch
notifications.

```text
PS5 → USB3.0 Video → StreamerRuntime → FrameHub / ClipBuffer
                                                ├─► /live.jpg ──► Glass app cinema pump
                                                ├─► /api/situation ─► clutch HUD + haptics
                                                └─► POST /api/clip ─► clips/ on the PC
                          _qoresence._tcp ◄──── mDNS (deck) ──► NSD scan (phone)
```

## View it

1. PC: `python -m qoresence.cli --play --deck --deck-bind 0.0.0.0`
   Optional: `pip install 'qoresence[glass]'` for mDNS broadcast.
2. Same Wi-Fi, phone browser: `http://<pc-ip>:8765/glass.apk` (or rebuild
   locally — see Build). Enable “Install unknown apps” for the browser.
3. Open **Qoresence Glass** on the same Wi-Fi → tap the found PC (or type
   `192.168.x.x:8765`).
4. Live feed should badge `LIVE · CINEMA`. Home key pops the glass into
   picture-in-picture.

A previous-session APK at `qoresence-glass-debug.apk` is a stale MJPEG
shell. Rebuild after this change.

## Build

```powershell
cd native
.\build-apk.ps1
# → android\app\build\outputs\apk\debug\app-debug.apk
```

Needs JDK 21 + Android SDK (paths in `build-apk.ps1`).

## Why this is not the PWA

| | iPhone PWA (`/mobile.html`) | Android app (`native/www`) |
|--|--|--|
| Video | WebRTC + MJPEG | `/live.jpg` cinema pump (WebView cannot play MJPEG) |
| Pairing | QR / typed IP | NSD mDNS + typed IP |
| Clutch | none | haptic + heat bar + why-line |
| Background | none | local clutch notification |
| Home key | tab backgrounded | 16:9 picture-in-picture |
| Score | `—` until locked | `—` until locked |

## Invariants

- No capture on the phone.
- Same Wi-Fi only. No STUN/TURN, no public stream.
- mDNS never advertises on loopback.
- Cleartext HTTP is allowed only so the LAN deck (`http://`, not https)
  can be fetched. Not a license for a public bind.
- `POST /api/clip` writes on the **PC**.
