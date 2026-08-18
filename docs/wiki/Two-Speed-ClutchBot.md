# Two-Speed ClutchBot

ClutchBot evolved purpose: **act on video + controller in realtime**; **OCR confirms** facts.

- Fast path: `FastMomentEngine` + IVC coupling — soft chat (no score digits), clip intent, arm prediction
- Confirm path: existing `MomentScorer` — real scores, resolve predictions
- **Local HUD digit lock**: when OCR/VLM are offline, a template-free 0–9 classifier reads the profile-aware scorebug crop and returns a `(home, away)` pair only when both sides are independently readable. Fail-closed — an empty HUD bar returns `None`, never `0-0`.

Full doc: [docs/TWO_SPEED_CLUTCHBOT.md](https://github.com/ConWan30/Qoresence/blob/main/docs/TWO_SPEED_CLUTCHBOT.md)

```text
python -m qoresence.cli --play --deck --controller --streamer-device 0 --streamer-fps 60
```
