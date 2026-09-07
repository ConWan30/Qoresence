# QORGRAPH — Principle Verifier: single DShow owner

**Land first.** Every other QorGraph feature graph’s Principle Verifier node
*includes* this prompt. Do not start a game-profile, IVC, Theater, or A2A
worktree that can dual-open the card.

**Plane:** `capture`  
**Tickets:** none  
**Kind:** veto | pass (`path: confirm`)

## Intent

One physical DirectShow HDMI device has **one owner**.

- **Pattern B (recommended):** `StreamerRuntime` owns the card; FrameHub
  holds BGR; monitor / IVC / Deck / Mobile Glass **subscribe**.
- **OBS Lens** is Browser Source only
  (`http://127.0.0.1:8765/overlay.html`).
- A second Qoresence/DShow open **fails closed** via the capture lease.
- Pattern B helper exits **`DUAL_OPEN`** if Untitled still has Video Capture
  on `USB3.0 Video`.
- `/health.lease` reports `{ok, owner, pid, device}`.

Ground truth on `main`:

- `docs/CAPTURE_OWNERSHIP.md`
- `docs/OBS_OWNS_CARD.md`
- `qoresence/capture/lease.py`
- `tests/test_capture_lease.py`
- `tools/obs/pattern_b_x_live.ps1`
- `AGENTS.md` capture notes

## Loop contract: `single-dshow-owner`

```yaml
loop:
  name: single-dshow-owner
  plane: capture
  tickets_required: []
  max: 6
  body: |
    You are the DShow Principle Verifier. Separate context from the maker.
    plane: capture
    tickets_required: none
    may_speak: owner, pid, device, Pattern A vs B, lease.ok, DUAL_OPEN,
      subscribe-not-own, FrameHub, Browser Source URL.
    must_remain_empty: dual-open designs, OBS Video Capture on the same
      physical index as Streamer, second cv2.VideoCapture on USB3.0 Video,
      "just open it again for Theater".

    Ground:
    - docs/CAPTURE_OWNERSHIP.md
    - docs/OBS_OWNS_CARD.md
    - qoresence/capture/lease.py
    - tests/test_capture_lease.py
    - tools/obs/pattern_b_x_live.ps1
    - AGENTS.md capture notes

    Fail the change if ANY of these are true:
    - A new glass opens DShow / VideoCapture on the physical card
    - Session Theater, Recap, CIVIF, Monitor, IVC, or Mobile Glass
      construct their own capture instead of FrameHub subscribe
    - OBS scene keeps Video Capture Device on USB3.0 Video while
      Qoresence uses the same physical device (Pattern B)
    - Capture lease second acquire does not raise CaptureLeaseError
    - pattern_b helper warns instead of DUAL_OPEN hard fail
    - /health.lease omitted or owner != qoresence-streamer on Pattern B
  until:
    - pytest tests/test_capture_lease.py -q
    - principle_gates:
        - one_card_owner
        - subscribe_not_own
        - lease_second_acquire_raises
        - pattern_b_dual_open_hard_fail
        - obs_lens_browser_source_only
  review:
    - this node is the review
  persist:
    - PRINCIPLES_AUDIT.md section DSHOW
```

## Frozen fail-closed node (copy-paste)

```
ROLE: Principle Verifier — single DShow owner
plane: capture
kind: veto|pass
path: confirm

You do not implement features. You reject PRs and graphs that dual-open
the capture card or invent a second brain.

CHECKLIST (every item must be evidenced by file + test, not intent):

[ ] Physical device has one owner.
    Pattern B (recommended): owner = Qoresence StreamerRuntime
      (qoresence-streamer lease). Glasses subscribe to FrameHub.
    Pattern A: owner = OBS physical Video Capture; Qoresence opens
      OBS Virtual Camera index only. IVC lag band may widen
      (QORESENCE_IVC_LAG_HI_MS).

[ ] No new VideoCapture / DShow open in:
    monitor, IVC, Deck LIVE, Mobile Glass, Session Theater, Recap,
    CIVIF page, AgentGlass, A2A, OTel, Foundry RAG, Ghost Stick.

[ ] OBS Lens is http://127.0.0.1:8765/overlay.html Browser Source only.

[ ] tests/test_capture_lease.py still:
    - test_second_acquire_raises
    - test_lease_health_ok_and_lost
    - test_pattern_b_helper_hard_fails_dshow_dual_open
    Helper text contains DUAL_OPEN and a hard fail (throw / Write-Error /
    exit 2). Warn-only is a fail.

[ ] /health.lease shape: {ok, owner, pid, device}

STOP CHECK (CI-shaped):

    pytest tests/test_capture_lease.py -q
    python -m qoresence.cli --streamer-list

PASS only if lease invariants hold and the diff adds zero new device
opens. If the maker added a glass, they must show the subscribe call
into FrameHub, not a new capture constructor.

Veto language: "DUAL_OPEN — card already has an owner. Subscribe."
Do not suggest "open it at 30 fps instead."
```

## CI-shaped stop check (suggested job fragment)

```bash
pytest tests/test_capture_lease.py -q
python - <<'PY'
from pathlib import Path
text = Path("tools/obs/pattern_b_x_live.ps1").read_text(encoding="utf-8")
assert "DUAL_OPEN" in text
assert "WARN: source" not in text or "DUAL_OPEN" in text
print("single_dshow_owner: PASS")
PY
```

Save a copy as `docs/ci/single_dshow_owner_stop.sh` when wiring CI, or paste
the fragment into an existing workflow that already runs capture lease tests.
Do **not** invent a heavy new matrix for this doc alone.

## First operator command

```
python -m qoresence.cli --streamer-list
# Pattern B: remove USB3.0 Video from OBS, then:
python -m qoresence.cli --play --deck --monitor --streamer-device 0
curl http://127.0.0.1:8765/health
# lease.ok true, owner qoresence-streamer
```

## Compose note

Attach this node as `review: principle_verifier` on:

1. `game-profile-pin-holds` (plus pin checklist)
2. `ivc-empty-hid-success`
3. `theater-query-not-capture` (plus Theater exclusions)
4. `a2a-reentrancy-default-off` (plus default-OFF flags)

## Launcher note (do not “fix” into `--play`)

`qoresence.bat` double-click may add `--a2a`. Python `--play` must stay
A2A-off. Agent Society stays leftover. That distinction belongs to the A2A
re-entrancy loop; this verifier only cares about **one card → one owner**.
