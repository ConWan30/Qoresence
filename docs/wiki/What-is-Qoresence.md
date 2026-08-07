# What is Qoresence?

Qoresence is a **local, opt-in observation layer** that:

1. Captures (or receives) live game video from a capture card or **OBS Virtual Camera**
2. Optionally reads **DualSense / DualSense Edge** HID
3. Builds a **situation model** (score, down, game context) from outcome + visual lobes
4. Emits a **causal event bus** (`session_id` + `clock_ns` + `source_lobe` on every event)
5. Renders **operator glasses**: Retina Deck (Lens + Theater), native Retina Monitor, LIVE MJPEG
6. Optionally runs **ClutchBot** for Twitch chat / clips / predictions

## Planes

| Plane | Question it answers |
|-------|---------------------|
| Capture | What frames / buttons / OCR just happened? |
| Situation | What is the game state *now*? |
| Operator glass | Can I *see* and *act* locally without cloud? |
| Social | Should chat/clips fire? (optional) |
| Research | Fusion / trio-retina validation? (optional, off) |

## Explicit non-goals

- Claiming humanity or “you are a real gamer” as a product feature  
- Anti-cheat or legitimacy verification  
- Dual-opening the same physical DirectShow device as OBS  
- Using Twitch stream delay as the sync master clock  
- Requiring blockchain for the MVP  

## Principles

1. **All lobes default OFF** — operator enables deliberately  
2. **One physical card → one owner** (usually OBS)  
3. **Shared monotonic clock** joins modalities  
4. **Co-occurrence language** for input↔video (`coupling`), not “proof”  

## Who it is for

- Streamers running NCAA Football / CoD-class titles with HDMI + OBS  
- Operators who want local Foundry clips with button sidecars  
- Researchers exploring presence / causal multi-lobe stacks without truth-plane claims  
