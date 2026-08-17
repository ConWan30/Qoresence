# Native Glass — Android spectator app (Phase 2)

`Qoresence Glass` is a thin native Android wrapper around the Mobile Glass
PWA. It is a **view, never a capture owner** — same rule as the browser PWA
in `docs/MOBILE_GLASS.md`. The app adds three things the browser cannot:

1. **mDNS auto-pairing** — the phone scans Wi-Fi for `_qoresence._tcp` and
   lists every PC running `--play --deck --deck-bind 0.0.0.0`. No IP typing.
2. **Clutch haptics** — `Haptics.impact(HEAVY)` when `coupling.climax_score`
   crosses 0.4 on a new peak.
3. **Background clutch alerts** — a foreground service polls
   `/api/situation` every 5 s while the app is backgrounded and posts a
   local notification on a clutch moment (no push server, no cloud).

```text
PS5 → USB3.0 Video → StreamerRuntime → FrameHub
                                                ├─► /video MJPEG ──► Glass app <img>
                                                └─► /api/situation ─► clutch strip + haptics
                          _qoresence._tcp ◄──── mDNS (deck) ──► NSD scan (phone)
```

## Layout

```
native/
├─ capacitor.config.ts        # appId io.qoresence.glass, webDir www
├─ package.json               # @capacitor/android, app, haptics
├─ build-apk.ps1              # one-shot debug APK build (JDK21 + Android SDK)
├─ src/plugins/definitions.ts # QoreMdns + QoreBackground TS plugin types
├─ www/                       # bundled PWA shell (MJPEG, pairing, strip)
│  ├─ index.html              # native shell: absolute hostUrl, Capacitor hooks
│  ├─ manifest.webmanifest
│  ├─ sw.js
│  └─ icons/
└─ android/                   # Capacitor Android project (committed)
   └─ app/src/main/java/io/qoresence/glass/
      ├─ MainActivity.java          # registers QoreMdns + QoreBackground
      ├─ QoreMdnsPlugin.kt          # NSD discover(_qoresence._tcp)
      ├─ QoreBackgroundPlugin.kt    # startForeground / stopForeground / notify
      └─ QoreForegroundService.kt   # 5s situation poll → clutch notification
```

The deck-side counterpart is `qoresence/deck/mdns.py` + the
`/api/discover`, `/manifest.webmanifest`, `/sw.js`, `/icons/{name}` routes
on the Deck server (port 8765, same pilot lock as the rest of the Deck).

## Two shells, one rule

There are **two** Mobile Glass shells. Both are view-only:

| shell | served by | live URLs | pairing gate |
|-------|-----------|-----------|--------------|
| `qoresence/deck/mobile.html` (PWA) | the Deck | **relative** (`/video`, `/api/...`) | skipped — already on the Deck |
| `native/www/index.html` (app) | bundled in the APK | **absolute** (`hostUrl + /video`) | shown — NSD scan or manual entry |

The PWA skips its pairing gate when served from a real `http(s)://host`
origin (see `tests/test_mobile_glass_pwa.py::test_mobile_html_skips_pairing_when_served_from_deck`).
The native app always shows pairing on first run because it loads from a
bundled shell with no deck origin.

## Build (debug APK)

Prereqs (paths hard-coded in `build-apk.ps1`, adjust for your machine):

- JDK 21 at `C:\Users\Contr\jdk21\jdk-21.0.5+11`
- Android SDK at `C:\Users\Contr\android-sdk`
- Node + npm (for `npx cap`)

```powershell
cd native
.\build-apk.ps1
# → android\app\build\outputs\apk\debug\app-debug.apk
```

Sideload the APK to the phone (USB / Drive), enable "Install unknown apps"
when prompted, then open **Qoresence Glass**.

## Run (end-to-end)

1. PC: `python -m qoresence.cli --play --deck --deck-bind 0.0.0.0`
   - `--deck-bind 0.0.0.0` is the LAN opt-in. mDNS only advertises on a
     non-loopback bind.
   - Optional: `pip install 'qoresence[glass]'` to enable `zeroconf` mDNS
     broadcast. Without it the deck still serves `/api/discover` and the
     phone falls back to manual address entry.
2. Phone on the **same Wi-Fi**. Open Qoresence Glass.
3. First run: the app scans for `_qoresence._tcp` and lists found PCs.
   Tap one → live MJPEG + situation strip.
4. Background the app → clutch moments still notify (foreground service).
5. Verify no second capture device is opened on the PC.

## Permissions (Android)

Declared in `AndroidManifest.xml`:

- `INTERNET`, `ACCESS_NETWORK_STATE`, `ACCESS_WIFI_STATE` — fetch situation + MJPEG
- `CHANGE_WIFI_MULTICAST_STATE` — NSD mDNS discovery
- `VIBRATE` — clutch haptics
- `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC` — background clutch poll
- `POST_NOTIFICATIONS` — clutch notifications (Android 13+ runtime prompt)

## Security / invariants

- **No capture.** The app only reads `/video` (MJPEG) and `/api/situation`
  from the Deck. It never opens a capture card.
- **Same Wi-Fi only.** No STUN/TURN, no cellular relay, no public stream.
- **mDNS is LAN-opt-in.** `mdns.start_mdns` is a no-op on loopback binds;
  `discovery_info` reports `lan:false` honestly on `127.0.0.1`.
- **No score invention.** The strip shows `—` until `score_vlm_locked` /
  `scoreboard_locked` / `title_claim` is true — same rule as the PWA.
- **Foreground service is clutch-only.** It polls `/api/situation` at 5 s
  and posts a notification only on a real climax crossing. It is not a
  keep-alive for video.

## Non-goals

- Replacing the browser PWA. The PWA remains the primary mobile path; the
  native app is for users who want haptics + background clutch alerts.
- Cloud push notifications. All alerts are local, generated on-device from
  the Deck's situation API.
- Audio. Video-only, same as the PWA v1.
- iOS. Android-only for the pilot.

See also: `docs/MOBILE_GLASS.md`, `docs/WEBRTC_LIVE.md`, `docs/AGENT_GLASS.md`.
