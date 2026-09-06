# SEQGATE v0 — Sequence Gate Harness Protocol

**Slogan: Same frame or silence.**

Fail-closed **frame-license** for digit and claim speech. Clutch Lens, AgentGlass, MCP `get_observation`, and the overlay fallback only speak hard digits when Same-Seq + ticket + lock + fresh hold. Otherwise: dark / HOLD / `□–□`. Never last-good freeze.

Ichigo-style harness layers (Bind → Lease → Ticket → Fresh → Same-Seq → Abstain → Vocab) become Qoresence’s observation-plane novelty: a named gate over Null Digit + ticket-fresh + capture lease, not a second score path.

Ident Latch (#145) stays **HOLD** — SEQGATE is not Ident Latch.

---

## Protocol layers

| Layer | Law | Qoresence wire |
|---|---|---|
| **Bind** | Before speech/tool: stamp `clock_ns`, `frame_seq`, `path=fast\|confirm`, `plane=observation`, `kind=fact\|ticket\|veto\|hold` | FrameHub clock via `qoresence.sync.seqgate.bind` |
| **Lease** | Exclusive world resources: named single-open; second open fails closed | Existing capture lease (`qoresence/capture/lease.py`) + Spout subscribe. Glasses do not open DShow. |
| **Ticket** | Coupling ticket licenses heat/co-occurrence. ConfirmTicket + `score_vlm_locked` licenses digits/claims. Fast path never invents hard claims. | Ticket-clock law. `path=fast` → `path_fast` veto. |
| **Fresh** | Claims expire when `\|live_clock − ticket_clock\|` exceeds budget (default 8s / `8e9` ns, Theater `ticketFresh`) or crop/seq mismatch | `digit_void_reason` / glass `ticketFresh` |
| **Same-Seq** | UI + agent mouths must match LIVE `frame_seq` or blank | Dark Theater / Ghost Stick / `same_seq` |
| **Abstain** | Missing ticket/lock/fresh → explicit HOLD / Null Digit / `□–□` | Null Digit Glass |
| **Vocab veto** | Presence / coupling / co-occurrence only | Ban authorship, eligibility, humanity, anti-cheat, “you threw that” |

Digits are licensed only when **Bind + Ticket + Fresh + Same-Seq** hold. Lease is the exclusive-open law for the capture card, not a digit paint switch. Vocab vetoes free-text claims even when digits would pass.

---

## Qoresence adoption card

```yaml
seqgate:
  version: v0
  slogan: Same frame or silence.
  plane: qoresence-observation
  kind: [fact, ticket, veto, hold]
  path: [fast, confirm]
  fresh_budget_ns: 8000000000
  null_digit: "□–□"
  abstain: HOLD
  layers:
    bind: FrameHub clock_ns + frame_seq
    lease: capture lease (existing; do not reinvent)
    ticket: coupling=heat; confirm+lock=digits; fast never hard claims
    fresh: 8e9 ns or crop/seq mismatch
    same_seq: widget.frame_seq == live.frame_seq
    abstain: HOLD / Null Digit / □–□
    vocab: presence | coupling | co-occurrence
  mouths:
    clutch_lens: glass SPA LockbugStrip (pickBoard) + overlay.html fallback
    agent_glass: snapshot.seqgate + stripped unlicensed scores
    overlay: qoresence/deck/overlay.html SEQGATE_NULL
    mcp: get_observation / build_observation seqgate receipt
  operator_meter:
    health: /health seqgate + digit_integrity
    integrity_board: HOLD — empty tiles; do not invent UI chrome this PR
  never:
    - last-good freeze
    - Ident Latch (#145 HOLD)
    - path=fast digits
    - scoreboard_locked / board_locked as digit permission
    - authorship / eligibility / humanity / anti-cheat / "you threw that"
    - DualSense USB play (Bluetooth on PS5; USB Edge observe-only)
    - bounce LIVE / merge to main from this draft
  module: qoresence.sync.seqgate
```

---

## Speech

| Gate | Mouth |
|---|---|
| Licensed confirm + lock + fresh + same-seq | `14-10` (fact) |
| Missing ticket / unlocked / stale / crop / seq skew / VLM abstain | `□–□` (hold) |
| `path=fast` | `□–□` (veto) |
| Banned vocab | `HOLD` (veto) |

Unlicensed scores are stripped from AgentGlass `situation` so a raw snapshot cannot leak last-good digits. MCP `may_say` never includes unlicensed pairs. Overlay fallback paints `□–□` every frame from the live bag — it does not keep the previous pair.

---

## What this PR is not

- **Not Ident Latch (#145).** That issue stays HOLD.
- **Not a new Integrity Board UI.** Operator meter is `/health.seqgate` + existing `digit_integrity`. Empty Integrity Board tiles: HOLD note only.
- **Not a parallel score path.** SEQGATE calls `digit_void_reason` / ticket-fresh. Capture lease stays `qoresence.capture.lease`.
- **Not a DualSense play-path change.** Play stays Bluetooth on PS5; USB Edge observe-only.

---

## Verify

```powershell
python -m pytest tests/test_seqgate.py tests/test_digit_integrity.py tests/test_overlay_digit_gate.py tests/test_mcp.py tests/test_agent_glass.py tests/test_capture_lease.py -q
```
