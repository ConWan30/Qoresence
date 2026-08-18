# Native Glass

Android spectator cinema. Same FrameHub / ClipBuffer as Theater. The phone is a **view**, never a capture owner.

Safari cannot do these. The APK can:

- JPEG cinema pump of `/live.jpg` (WebView cannot play MJPEG)
- NSD mDNS for `_qoresence._tcp`
- clutch haptic + heat bar (`coupling.climax_score`)
- 16:9 picture-in-picture (pump keeps running in the overlay)
- keep-awake + local clutch notifications
- `POST /api/clip` writes the HDMI ring on the **PC**

iPhone stays on Option A: Safari → Add to Home Screen (`/mobile.html`).

```text
python -m qoresence.cli --play --deck --deck-bind 0.0.0.0
# sideload native/android/app/build/outputs/apk/debug/app-debug.apk
```

Empty buffer: `/live.jpg` is 503. Score strip stays `—` until locked.

Full doc: [docs/NATIVE_GLASS.md](https://github.com/ConWan30/Qoresence/blob/main/docs/NATIVE_GLASS.md)
