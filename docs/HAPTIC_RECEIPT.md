# Haptic Receipt Clock (`haptic_receipt-1`)

Observation plane only. This is the **novel CIVIF integration**: a third clock that joins three rails in one fail-closed envelope. It is **not** a rumble visualizer, OBS overlay, or DualSense writer.

## Why this exists

IVC already joins **HID-in** with **HDMI frame stamps**. Session Theater already shows a **locked HDMI board**. The haptic probe already records **output rumble / IMU echo** when this host can see them.

None of those alone is the product. The missing join is:

> Did this host feel a pad pulse **in the same window** as a **licensed HDMI lock** while the pad was **bodied here**?

That three-rail receipt is what later Theater / clip sidecars may consume — only after Qoreeval. Until then `public_surfaces` stays `false` and `haptics_confirmed` stays `false`.

## The three rails

| Rail | Licenses when | Stays dark when |
|------|----------------|-----------------|
| `hid_in` | This host has HID reports | DualSense left on the PS5 (empty HID) |
| `hdmi_lock` | `board_locked` or `score_vlm_locked` **and** a ConfirmTicket id | Flag-only lock, no ticket; unlocked board |
| `haptic_out` | `haptic_transient` on `hid_output` or `imu_echo` | PS5 BT rumble on a charge-only USB cable; probe off; no pulse |

`coupled` is true **only** if every rail licenses. Score digits appear **only** if `hdmi_lock` licenses. Button names never appear. `controller_bodied` is not a field on the receipt (use `rails.hid_in`).

## Honest physics

Sony does not mirror console haptic **output** onto a laptop USB charge pipe. A PS5-bound Edge plus USB-to-laptop is a licensed **dark** receipt (`haptic_receipt_dark`), not a synthetic zero pulse.

Laptop-bodied USB DualSense can expose `hid_output` and/or `imu_echo`. That is the only path where all three rails can light.

## What this is not

- Not streamer / Theater / MCP payload (hold until Qoreeval).
- Not a write to the pad.
- Not `haptics_confirmed`.
- Not Streamr / DePIN / off-box distribution.

## Code

- Builder: `qoresence.sync.haptic_receipt`
- Existing pulse log: `haptic_obs-1` via `--haptic-probe` / `QORESENCE_HAPTIC_PROBE=1`
- Offline co-occurrence metrics (not this clock): `scripts/haptic_corroboration.py`

```python
from qoresence.sync.haptic_receipt import receipt_from_tick_and_obs, validate_receipt

rec = receipt_from_tick_and_obs(civif_tick, haptic_obs_row)
assert validate_receipt(rec) == []
```
