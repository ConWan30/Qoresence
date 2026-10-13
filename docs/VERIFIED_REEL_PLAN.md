# Verified Highlight Reel — design plan

Status: **proposal** (docs only, nothing built yet). Bots propose; ConWan30 decides.

## 1. What it is

For each **locked** score change, Qoresence:

1. pulls the clip for that moment,
2. checks the DualSense controller input trace from the window just before the change,
3. issues a signed receipt that ties the frames, the score read, the input trace and the clock together, and
4. stitches the receipted clips into a ~60 s reel (landscape 16:9 or vertical 9:16) with a gold locked-score overlay and optional narration.

A viewer, or a later verifier, can check that each clip shows a score Qoresence actually locked and that a human was driving a controller in the seconds before it.

### Non-goals

- This is **not** a wagering, settlement or anti-cheat oracle. The receipt proves the local observation chain, not who held the controller or whether the game was fair.
- It does not prove humanity. The input trace *corroborates*; it does not *authenticate*.
- No cloud signing. The key stays local.

## 2. Existing modules this builds on

| Need | Existing module (main) | Notes |
|---|---|---|
| Score lock | `qoresence/vision/confirm_ticket.py` (`ConfirmTicket`, `ticket_is_licensed_lock`, `ConfirmTicketBook`), `qoresence/vision/scoreboard_lock.py`, `qoresence/vision/local_scorebug/` | Only a licensed lock can trigger a clip. `ticket_id`, `crop_hash`, `frame_seq`, `observed_clock_ns` are already on the ticket. |
| Frame identity | `qoresence/monitor/frame_hub.py` (`seq`, `clock_ns`, `crop_hash`, luma ring) | Same monotonic clock as HID. |
| Clip ring (Foundry) | `qoresence/vision/clip_buffer.py` (`HdmiClipBuffer`, `export_clip`, `flush_armed_clips`, `_write_buttons_sidecar`, `_write_coupling_sidecar`, `_write_observation_sidecar`) | Already writes `clips/<stem>.buttons.json` from the InputRing. |
| OBS replay (alt source) | `qoresence/obs/bridge.py` on PR #280 (`ObsBridge`, `save_replay_buffer`, `create_chapter`; fires only on a genuine locked increase, rate-limited) | Used when OBS owns the encode (Pattern A). |
| Input trace | `qoresence/sync/input_ring.py` (`InputEvent`, `InputRing`), `qoresence/sync/hid_seq_line.py` (`snapshot_at_seq`, `get_window`), `qoresence/sync/hid_domain.py` (PLAY vs OBSERVE pad), `qoresence/sync/play_phrase.py` | Only `HidDomain.PLAY` events count. Laptop USB Edge = OBSERVE, never corroborates. |
| Coupling / IVC | `qoresence/sync/coupling_ticket.py`, `qoresence/sync/ivc.py`, `qoresence/sync/event_bind.py` | Input-to-video binding at frame-seq level. |
| Receipts | `qoresence/studio/receipt.py` (`ReelReceipt`, `write_receipt`), `qoresence/sync/haptic_receipt.py` (rails + `validate_receipt`), `qoresence/compose/clock_notary/` (`envelope.py` canonical JSON + clock commitment, `io_ledger.py`, `verify.py`) | Reuse canonical JSON (`sort_keys`, compact separators) and the clock-notary commitment. |
| Ledger | `qoresence/observability/jev_ledger.py` (`qoresence.jev.ledger.v0`, `licenses_digits` is always False) | Each receipt gets one Jev row (pack `verified_reel`, added to the known-pack list). The ledger still never mints digits. |
| Ship receipt | `qoresence/deck/rivalatch_knock.py` (Rivalatch knock/lodge) | Optional: lodge the *reel manifest hash*, never the media. |
| Signing | Ed25519 is used in `qoresence/trio/payload.py` (device-key signature field) | Same key type. New local key file; see §6. |
| Reel render | `qoresence/studio/ghost_cut.py`, `reel_queue.py`, `render_command.py`, `qoresence/foundry/highlights.py` (`rank_highlights`), `qoresence/foundry/narrative*.py` | Ghost Cut renders; the narration text comes from the narrative engine and may only cite licensed tickets. |

## 3. Architecture

```
 HDMI card ──► Streamer (grabber) ──► FrameHub(seq, clock_ns, crop_hash)
                                    ├─► clip_buffer ring (Foundry)
                                    └─► scoreboard-lock worker ─► ConfirmTicketBook
 DualSense (PLAY) ──► HID lobe ──► InputRing / HidSeqLine (same clock_ns)

 ConfirmTicketBook ──(licensed lock, score changed)──► ReelWitness  (new, off hot path)
        ReelWitness:
          1. clip   := clip_buffer.export_clip(pre=Tpre, post=Tpost)  | OBS save_replay_buffer
          2. frames := hash K sampled frames + the lock frame (sha256 of raw BGR bytes)
          3. trace  := InputRing window [t_lock - W, t_lock], PLAY domain only
          4. corroborate(trace) -> verdict + features
          5. receipt := canonical JSON -> sha256 -> Ed25519 sign
          6. write clips/<stem>.vreceipt.json ; JevLedger.append(pack="verified_reel")
 ReelAssembler (offline / on demand):
     select receipts (verified first) -> Ghost Cut render -> gold overlay -> narration -> reel.mp4 + reel.manifest.json (signed)
```

ReelWitness runs on its own worker thread with a bounded queue (drop the oldest and log it). It must **never** run on the capture, HID or bus threads (AGENTS.md Rule 1, and see PR #281).

## 4. Data flow and timing

- `t_lock`: `observed_clock_ns` of the licensed `ConfirmTicket` whose pair differs from the previous licensed pair (using `board_sides_same` / `side_same` for orientation).
- Clip window: `[t_lock - 12 s, t_lock + 4 s]` by default. Scores show up on the scorebug after the play, so the play is in the pre-roll.
- Input window: `W = 15 s` before `t_lock`, clipped to the clip's start.
- All timestamps are `time.monotonic_ns()`, the shared FrameHub/HID clock. The receipt also records a wall-clock `created_utc` (informational only, not trusted).

## 5. Input corroboration

Features computed from PLAY-domain `InputEvent`s in the window:

| Feature | Definition | Why |
|---|---|---|
| `input_density_hz` | edges per second over W | An idle pad means no human play |
| `menu_burst` | ≥ N face/d-pad presses within 4 s, followed by a quiet gap (play-call screen) | Matches Madden/CFB play selection |
| `snap_edge_ns` | first X/A press (or `play_phrase` "snap") after the menu burst | Snap timing |
| `snap_to_lock_s` | `t_lock - snap_edge_ns` | Must be plausible (e.g. 3–40 s) |
| `stick_activity` | analog pose variance after the snap | Ball carrier / QB movement |
| `frame_coupling` | from `coupling_ticket` / `ivc` when available | Input-to-motion causality hint |

Verdicts:

- `corroborated`: density ≥ floor, snap found, snap_to_lock in range, PLAY domain.
- `weak`: some input but missing the snap or out of range.
- `unverified`: no PLAY input in the window, OBSERVE-only input, ring gap, or clock skew over the threshold.

Thresholds live in a profile per title (Madden / CFB), next to `local_scorebug/profile.py`.

## 6. Receipt schema (`qoresence.verified_reel.receipt.v0`)

```json
{
  "schema": "qoresence.verified_reel.receipt.v0",
  "session_id": "…",
  "receipt_id": "sha256(canonical body)[:32]",
  "clock": {"t_lock_ns": 0, "clip_start_ns": 0, "clip_end_ns": 0, "clock_source": "monotonic_ns", "created_utc": "…"},
  "score": {
    "ticket_id": "…", "source": "local_scorebug|quicksilver|…", "model": "…",
    "prev_pair": [7, 3], "pair": [14, 3], "home_left": false,
    "crop_hash": "…", "frame_seq": 0, "licensed": true
  },
  "frames": {"hash_alg": "sha256", "lock_frame": "…", "samples": [{"seq": 0, "clock_ns": 0, "sha256": "…"}], "merkle_root": "…"},
  "clip": {"source": "foundry_ring|obs_replay", "path": "clips/…mp4", "sha256": "…", "duration_s": 16.0},
  "input": {
    "domain": "play", "window_ns": [0, 0], "events": 0,
    "trace_sha256": "sha256(canonical list of InputEvent.to_dict())",
    "features": {"input_density_hz": 0, "menu_burst": true, "snap_edge_ns": 0, "snap_to_lock_s": 0},
    "verdict": "corroborated|weak|unverified", "reasons": []
  },
  "label": "verified|unverified",
  "build": {"git_sha": "…", "profile": "madden27_standard_v1", "pack_sha16": "…"},
  "signature": {"alg": "ed25519", "key_id": "sha256(pubkey)[:16]", "sig": "hex"}
}
```

- The body is canonical JSON, the same as `clock_notary/envelope._canonical` (sort_keys, compact, ASCII). The signature covers the body minus `signature`.
- The raw input trace stays local by default (`clips/<stem>.buttons.json` already exists). Only its hash is in the receipt. Sharing the trace is opt-in, for privacy.
- Key: `~/.qoresence/keys/reel_ed25519` (0600), generated on first use, never leaves the machine, public key exported as `reel_ed25519.pub`. A verifier CLI (`python -m qoresence.studio.verify_reel`) re-hashes the clip, frames and trace and checks the signature.
- Jev ledger row: `pack="verified_reel"`, payload `{receipt_id, label, verdict, ticket_id}`, `licenses_digits: false`.

## 7. Fail-closed rules

1. **No licensed lock → no clip.** Only `ticket_is_licensed_lock(ticket)` with a pair change triggers. Held, stale or blank boards never do. Local/cloud disagreement (`choose_board → cross_check_disagree`) never does.
2. **No input corroboration → `label: "unverified"`.** The clip may still go in the reel, but with a visible "UNVERIFIED" tag and no gold overlay.
3. **OBSERVE-domain HID never corroborates** (`hid_domain.py` law).
4. A decrease or reset of the score (new game, correction) creates no clip. It only resets the baseline (same as the OBS bridge).
5. A missing frame hash, clip hash mismatch, ring gap over 500 ms, or clock skew over 250 ms between the HID and video clocks → `unverified` with the reason recorded.
6. Signing failure (no key, bad permissions) → no receipt is written and the reel refuses that clip. Never write an unsigned receipt that looks like a signed one.
7. Narration may only state digits that a receipt in the reel carries. No narration for `unverified` clips beyond "unverified play".
8. Everything is default OFF behind `--verified-reel` / `QORESENCE_VERIFIED_REEL=1`. `--play` alone does not enable it.

## 8. Reel assembly

- Pick up to ~60 s: verified clips first, then by `rank_highlights` score, in chronological order.
- Per clip: trim to `[snap - 2 s, t_lock + 2 s]` when a snap was found, otherwise the default window.
- Overlay: gold locked score (`pair`) appears **only from `t_lock` onward**. A small receipt tag shows `receipt_id[:8]` and a ✓ (verified) or "UNVERIFIED".
- Formats: 1920×1080 landscape, plus a 1080×1920 vertical with the scorebug band cropped and enlarged.
- Optional narration: TTS from `foundry/narrative_engine.py`, limited to ticket-licensed facts.
- Output: `reel.mp4` + `reel.manifest.json` (ordered receipt_ids, reel sha256, Ed25519 signature). Optionally lodge the manifest hash with Rivalatch.

## 9. MVP milestones

**M1: Receipt per lock (no reel).**
ReelWitness worker; Foundry ring export on a licensed change; frame hashes; input window + verdict; Ed25519 receipt; Jev row; verifier CLI. Fixture-driven (recorded FrameHub + InputRing replays, `dualsense_fixture.py`).
*Done when:* a 20-minute recorded Madden session produces one receipt per real score change, zero receipts on holds or decreases, and the verifier passes them.

**M2: Reel v0.**
Ghost Cut assembly, gold overlay, landscape + vertical, signed manifest, Studio button. The OBS replay source as an alternative to the Foundry ring when the PR #280 bridge is on.

**M3: Corroboration quality + narration.**
Per-title thresholds tuned on labelled sessions (CFB + Madden), coupling/IVC features, narration, optional Rivalatch lodge, and a public verifier page that checks the signature in the browser.

## 10. Test plan

- **Unit:** canonical body → stable `receipt_id`; sign/verify round-trip; a tampered clip, trace or score fails verification; unknown schema fails.
- **Fail-closed:** unlicensed ticket → no clip; disagree → no clip; decrease → baseline only; OBSERVE HID → `unverified`; key missing → no receipt; ring gap → `unverified`.
- **Corroboration:** synthetic InputRing traces (idle, menu burst + snap, mashing with no snap, OBSERVE only) → expected verdicts.
- **Concurrency:** ReelWitness never blocks the capture loop or HID (patterned on `tests/test_deadlock_regression.py` and `tests/test_capture_rebind_race.py`). Bounded queue drop is logged.
- **Integration:** a recorded session replays through FrameHub, scoreboard lock and ReelWitness. Count receipts, then run the verifier on all of them.
- **Reel:** the overlay never shows digits before `t_lock`, and the manifest hash matches the reel bytes.
- **Live (manual):** one Madden and one CFB session on the laptop with a PS5 pad, eye-checked.

## 11. Prior art & novelty

| Prior art | What it does | Gap this plan addresses |
|---|---|---|
| **PLLAY Outcomes Oracle** (pllay.io/oracle) | Vision AI reads recorded gameplay clips and settles outcomes with an evidence_uri and settlement_id. Its own page says "Game telemetry and other evidence sources: **Designed, not built**. Every title is video-only today." Live outcomes need a reviewer. | Here the evidence is local, on-device, and **multi-modal at capture time**: a video lock plus the controller HID trace on a shared monotonic clock, in one signed receipt. Not a settlement product. |
| **Eklipse** | AI auto-clipping of stream highlights and short-form (vertical) conversion | Clips are chosen by AI/engagement signals and carry no cryptographic evidence of score or input. |
| **Braket** | Skill-gaming / competitive match platform (result verification for head-to-head play) | Result handling depends on the platform and is not tied to a local signed frame + input receipt. *Confirm Braket's current verification method before citing it externally.* |
| **US 11,087,583** (Everi Games, "Apparatus and Methods for Facilitating Wagering on Games Conducted on an Independent Video Gaming System"; division of US 10,565,818; continued as US 11,881,077) | Wagering on outcomes of independent video games via an interface to the game system | Our plan is not wagering, but outcome capture from an independent console overlaps in subject. **Needs freedom-to-operate review.** |
| **US 11,420,129** | Cited by the user as relevant prior art; title and assignee **not verified in this pass** | Counsel to pull the claims. |

Elements that may be new together (not a legal opinion):
(a) lock-gated clip extraction, where an OCR/VLM score change is the only trigger;
(b) corroboration from controller-input timing (menu burst → snap → score) inside a pre-lock window;
(c) one Ed25519 receipt binding frame hashes, score readout, input-trace hash and a shared monotonic clock;
(d) fail-closed labeling ("unverified") carried visibly into the published reel.

**Recommendation:** get patent counsel to do a prior-art and freedom-to-operate review, covering at least the Everi family (10,565,818 / 11,087,583 / 11,881,077) and 11,420,129, **before** any commercialization, public claim of novelty, or wagering/settlement-adjacent use. Do not file or publish claims based on this doc alone.

## 12. Open questions

- Should the input trace be shared (it raises privacy concerns), or only its hash plus features?
- Key rotation, and binding the key to the device (TPM / Windows Hello) in M3?
- Is OBS replay or the Foundry ring the canonical source when both are present? Proposal: the Foundry ring, because Qoresence controls the frame hashes.
