# Two-Speed ClutchBot

ClutchBot evolved purpose: **act on video + controller in realtime**; **OCR confirms** facts.

- Fast path: `FastMomentEngine` + IVC coupling — soft chat (no score digits), clip intent, arm prediction  
- Confirm path: existing `MomentScorer` — real scores, resolve predictions  

Full doc: [docs/TWO_SPEED_CLUTCHBOT.md](https://github.com/ConWan30/Qoresence/blob/main/docs/TWO_SPEED_CLUTCHBOT.md)

```text
python -m qoresence.cli --play --deck --controller --streamer-device 0 --streamer-fps 60
```
