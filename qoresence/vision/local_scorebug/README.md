# Local scorebug reader (keyless) — phase 1: Madden NFL 27

Reads the score, game clock and quarter straight off the HDMI frame, on the
PC, with no cloud key and no model download (numpy + OpenCV only, about 1 ms a
frame). It answers only when it is sure; otherwise it stays blank.

## What it does

1. **Find the strip.** Cut the bottom band of the frame by fraction (y from
   330/360), scale it to the 640 px reference width, and find the Madden logo
   with a template match (±3 px). Blank if the logo is not there (another
   skin, a menu, a replay), if the white score panel is covered (banners,
   stat overlays, TOUCHDOWN), or if the dark clock box is missing.
2. **Read the digits.** Each score digit is cut out as ink, normalised to
   10x14 and compared with per-digit templates. A digit must beat an
   absolute floor (NCC ≥ 0.70) **and** the runner-up by a margin (≥ 0.08).
   Its hole layout must also fit: no learned digit has two holes, a 0 has one
   hole across the middle, a 9 one hole above it, a 3 none. Clock digits use
   their own templates (≥ 0.93, margin ≥ 0.06), the quarter word its own
   (≥ 0.85, margin ≥ 0.05). The red final-seconds clock always blanks.
3. **Agree over time.** The same (left, right, quarter) must be read on 3
   sampled frames at least 200 ms apart, spanning at least 400 ms. Any blank,
   a different reading, a gap over 2 s, a new session or a game clock that
   runs backwards starts over. A suspicious jump from the last agreed score (a
   drop, both sides moving, a non-football increment) needs 9 reads over 2 s,
   which is the local version of the cloud re-read.
4. **Mint through the normal path.** The agreed board goes to the same
   ConfirmTicket mint as a cloud read, labelled `source="local_scorebug"`, and
   is bound to the frame it read (frame seq, clock, crop hash; 8 s age limit).
   Every existing refusal still applies: 0-0 and empty crops are not licensed,
   the grounded-scorebug rule (clock and quarter must be present), the
   impossible-jump re-read, and blank on doubt.

## When it runs

| Setup | Behaviour |
|---|---|
| No cloud key (default) | Local reader **on**. It is the only score reader for Madden. |
| Cloud key set | Local reader **on**. A sure local read may lock; the cloud read cross-checks it. If they disagree, the board is blank until they agree. If the local reader is blank, the cloud path works exactly as before. |
| `QORESENCE_LOCAL_SCOREBUG=0` | Off. The cloud path only (as before this PR). |
| `QORESENCE_LOCAL_SCOREBUG=1` | Forced on (same as default today). |
| College Football profile/title | Skipped (phase 1 is Madden only). |

`/health` shows `local_scorebug` (reads, agreed, last blank reason, cross-check
disagreements).

## Known gaps (stays blank)

- **Digit 8 in the score.** None of the box clips has an 8, so there is no
  template, and none is invented. A score with an 8 (8, 18, 28, 38 …) stays
  blank. The hole check covers the risk: in a probe that inks real 0 glyphs
  into 8 shapes, all 342 variants blank (286 would have read as another digit
  without the hole check).
- **Dark primetime / compact skin.** Not learned; blank.
- **Red clock in the final seconds**, **overtime** (no OT template) and
  **clocks of 10:00 or more** (all captures use 4-minute quarters): blank.
- **1st quarter** comes from one clip; clock digits 6, 7, 9 have few samples.
- **No native 720p/1080p captures** yet: scaling is tested by resizing
  640x360 frames.
- Team names are not read (the cloud path or profile still supplies them).

## Eval on the box clips (Oct 8, 2026)

`scripts/eval_local_scorebug.py`, 14 HDMI clips + 2 stills (Sept 6–12, 2026
sessions, 640x360). LOCO = each clip read with templates built without it.

| Set | Mode | Correct | Blank | Wrong |
|---|---|---|---|---|
| Madden standard, labelled 1 fps frames (226 with a score) | LOCO | 168 | 58 | 0 |
| Madden standard, every decoded frame through agreement (2605 scored) | LOCO | 1941 | 664 | 0 |
| Madden standard, no readable score (590 frames) | LOCO | n/a | 590 | 0 |
| Madden dark skin (779 frames) | any | n/a | 779 | 0 |
| College Football (1523 frames) | any | n/a | 1523 | 0 |
| Synthetic-8 probe (342 shapes) | shipped | n/a | 342 | 0 |

With the shipped pack (in-sample) the clip-mode standard row is 2147 / 458 / 0.
Every leave-one-digit-out run (remove one digit's template, read all frames
with that digit) blanks: 621 score glyphs and 646 clock reads, 0 wrong.

## Regenerating templates after a game patch

When Madden changes the scorebug look, the reader goes blank (the logo or panel
check fails). That is safe. To teach it the new look:

1. Record a few clips at the capture resolution with the new scorebug,
   including several different scores, all four quarters, and as many digits
   as possible (especially 8).
2. Pull 1 fps frames, for example
   `ffmpeg -i clip.mp4 -vf fps=1 frames/<clip>_%03d.jpg`.
3. Add rows to `labels/madden27_box_labels.json`: `frame`, `clip`, `skin`
   (`madden_standard`, `madden_dark`, `cfb` or `none`), `left`, `right`,
   `quarter` (`1st` … `4th`), `clock` (`M:SS`, or `?` if you cannot see it),
   and `train: false` for frames in mid-animation. **Check every label by eye
   on an enlarged crop.** A wrong label teaches a wrong digit.
4. If the strip moved, update the boxes in `profile.py` (pixels at 640x360)
   and bump `layout_version`.
5. Build the pack:
   `python -m qoresence.vision.local_scorebug.build_pack --labels qoresence/vision/local_scorebug/labels/madden27_box_labels.json --frames <frames dir> --out qoresence/vision/local_scorebug/packs/madden27_standard_v1.npz --note "<what changed>"`
   The report lists glyph counts and `missing_score_digits`. Check that
   `score_hole_counts` still fits `score_hole_rules` in `profile.py`.
6. Evaluate. **Wrong must be 0:**
   `python scripts/eval_local_scorebug.py --labels … --frames … --loco --eight-probe [--clips <dir with the .mp4s>]`
   `--loco` rebuilds the pack without the clip under test, so the numbers
   reflect a session the reader has not seen.
7. Run `pytest tests/test_local_scorebug_*.py`. The fixture crops in
   `tests/fixtures/local_scorebug/` may need refreshing for a new look.

## Files

- `reader.py`: per-frame reader (`ScorebugReader`, `TemplatePack`, `FrameRead`)
- `glyphs.py`: ink masks, segmentation, NCC and the hole-layout check
- `profile.py`: Madden 27 standard strip geometry and gates
- `agreement.py`: multi-frame agreement window
- `service.py`: flag, sampling, cloud cross-check, health; called by
  `FootballScoreboardExtractor`
- `build_pack.py`: builds `packs/*.npz` from labelled frames
- `packs/madden27_standard_v1.npz`: shipped templates (about 16 KB)
- `labels/madden27_box_labels.json`: the frame labels the pack was built from
  (labelled by eye by Grok Bot, not owner-verified; the frames themselves are
  the owner's clips and are not committed)
