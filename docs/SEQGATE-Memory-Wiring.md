# SEQGATE × Memory Engineering — Conceptual Wiring (v0)

**Slogan triad**
- Harness wraps the **model**
- Memory wraps the **operator** (KingWilliam / Grok Bot memory engineering)
- SEQGATE wraps the **frame** (Qoresence)

**Product rule:** sell the **license**, not the lore. Dark > last-good. Revenue after Qoreeval density.

Memory is a **third glass** on the FrameHub clock — not a loophole around Same frame or silence.

---

## Topology

```text
LIVE FrameHub (clock_ns / frame_seq / crop_hash)
        │
        ▼
SEQGATE (Bind · Lease · Ticket · Fresh · Same-Seq · Abstain · Vocab)
        │
        ├── mouths     AgentGlass / get_observation / overlay
        ├── memory     SessionMemory / Qoremem envelopes
        └── clips      Foundry sidecars
                │
                ▼
LICENSE / RECEIPT export only if gate PASS
```

## Write path

Every session-brain memory write carries:

| Field | Law |
|---|---|
| `clock_ns` | Required. FrameHub monotonic. `0` is a real stamp, not missing. |
| `frame_seq` | Required. Same `frame_seq` as last accepted write → **NOOP**. |
| `crop_hash` | Key required. Explicit empty `""` is honest (no crop). Missing key → refuse. |
| `path` | `fast` \| `confirm` |
| `seqgate` | `licensed` \| `hold` |
| `reason` | Required non-empty (SEQGATE reason or hold). |
| `ticket_id` | Required when `seqgate=licensed` (hard claims). |

`path=fast` + `seqgate=licensed` is refused (`path_fast`). Fast writes may keep stamp fields as `seqgate=hold`. `persist=False` never promotes to verified recap. Empty HID still advances on FrameHub. Never emit-under-lock / under grab lock.

Module: `qoresence.sync.seqgate.accept_memory_write` → `SessionMemory.record(..., stamp=)`.

## Read / speech path

Hard claims from memory only if SEQGATE licenses **that** `frame_seq` as fresh against LIVE. Historical `seqgate=licensed` is a receipt, not a mouth.

| Gate | Mouth |
|---|---|
| Memory stamp missing | `□–□` / `unstamped` |
| Memory `frame_seq` ≠ live `frame_seq` | `□–□` / `seq_skew` — never last-good freeze |
| Memory clock aged past fresh budget | `□–□` / `ticket_stale` |
| `path=fast` | `□–□` — stamp fields may pass; **no invented digits** |
| Licensed confirm + lock + fresh + same-seq | Stamp fields pass; digits only if confirm-locked |

Recap empty when `not_persisted`. Clips need sidecar; Ident-on-frame → no clip. Ident Latch (#145) stays HOLD.

Module: `qoresence.sync.seqgate.license_memory_speech`. Mouths: `AgentGlass.snapshot(memory_entry=)` and MCP `build_observation(..., memory=)`.

## Landing order

card → pump → VLM lock → SEQGATE speech → memory densify / Foundry → Qoreeval before monetize claim.

## Anchors

FrameHub, capture lease, ConfirmTicket / ticket-fresh, Dark Theater / Ghost / Null Digit, AgentGlass `get_observation`, Qoremem envelopes, Foundry sidecars, `/health.seqgate`.

---

## SKU stubs (export contract only — **no payment**)

These are receipt shapes for a later export glass. This PR does **not** build checkout, meters-as-billing, or entitlements.

```yaml
skus:
  session_memory_pack:
    schema: seqgate-memory-pack-1
    export: jsonl
    fields: [clock_ns, frame_seq, crop_hash, path, seqgate, reason, ticket_id?]
    refuse: unstamped | missing_ticket | path_fast | same_seq_noop
  licensed_recap:
    schema: seqgate-licensed-recap-1
    requires: persist=true AND seqgate=licensed AND fresh AND same-seq
    else: empty / not_persisted / □–□
  clutch_brief:
    schema: seqgate-clutch-brief-1
    speak: may_say from get_observation only
  notary_receipt:
    schema: seqgate-notary-1
    export: jsonl receipt of gate PASS/HOLD; not a payment
  frame_write_meter:
    later: density after Qoreeval; not billed here
```

Fixture: `tests/fixtures/seqgate_memory_receipts.jsonl` (licensed write vs stale refuse).

---

## Hard vetoes

invent digits · last-good · authorship / eligibility / anti-cheat · Truth sync claims · play-off-Deck · DualSense-off-PS5 “fixes” · monetize before real-play density · emit-under-lock · Ident Latch (#145) as this work.

Play stays Bluetooth DualSense on the PS5; USB Edge is observe-only.

## Verify

```powershell
python -m pytest tests/test_seqgate_memory.py tests/test_seqgate.py tests/test_digit_integrity.py tests/test_agent_glass.py tests/test_mcp.py tests/test_deadlock_regression.py -q
```

## Done

In-repo docs · memory write refuses unstamped · one mouth refuses stale-as-live · one JSONL receipt fixture · tests · draft PR.
