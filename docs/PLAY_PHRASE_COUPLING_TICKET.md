# Play phrases + coupling ticket

Observation plane only. Compose with confirm tickets — never conflate.
Not authorship. Not anti-cheat.

## Sequence

1. **Play phrases** — typed join on the existing IVC sample.
2. **Coupling ticket** — licenses heat-speech the way confirm tickets license score digits.

## Phrases

Closed vocab: `IDLE` `HUDDLE` `SNAP` `SPRINT` `CUT` `RELEASE`.

| Phrase | Rule |
|---|---|
| `IDLE` | Menu / stale video / no analog |
| `HUDDLE` | Gameplay, no hold, no recent R2 edge |
| `SNAP` | R2 onset + frame motion in the join window |
| `SPRINT` | Fresh R2 hold + live video |
| `CUT` | Left-stick hold + frame motion |
| `RELEASE` | R2 falling after a hold |

`THROW` is forbidden (authorship). SNAP uses cheap `frame_motion_energy`, not Gemini.

## Coupling ticket

Domain `QORESENCE-COUPLING-TICKET-v0`.

Mint only when video is fresh and phrase ∈ {SNAP, SPRINT, CUT, RELEASE}.
Expires on `IDLE`/`HUDDLE` or ~400 ms.

Licenses: “controller heat”, “pad and picture”, FastMoment `input_spike`/`clutch_window`, A2A `reason=coupling`.
Confirm tickets still license score digits.

## Tests

- Menu + idle → `IDLE`, no ticket
- Fresh R2 hold + live frame → `SPRINT` + ticket
- Heat line without ticket → veto / skip
- Score speech still needs the confirm ticket
