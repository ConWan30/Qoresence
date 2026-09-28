# Frame License Bureau — One-Page SKU + Bot Runbook (v0)

**Product:** Sell *what may be said about a LIVE frame* — not clips-as-content, not coaching, not ads.  
**Slogan:** Same frame or silence. Sell the license, not the lore.  
**Factory:** Qoresence + SEQGATE/v0 + Memory third-glass + AgentGlass fleet.  
**Operator:** Contravious Battle · bots run; Human HOLD / spend / publish.  
**Gate to monetize:** Qoreeval repeated real-play density first. No payment plumbing in v0 — shape exports only.

Anchors: [`SEQGATE.md`](./SEQGATE.md) · [`SEQGATE-Memory-Wiring.md`](./SEQGATE-Memory-Wiring.md) · tip context `9d78c37` (stamped session-memory on `main`).

---

## 1. What buyers get (SKU menu)

| SKU | Deliverable | Gate | Who packages |
|-----|-------------|------|--------------|
| **A. Session Memory Pack** | JSONL: tickets + Same-Seq receipts + delay residual + `seqgate=licensed\|hold` | PASS stamps only in pack body; HOLD rows allowed as audit | Qoremem → Money making bot |
| **B. Licensed Recap / Clutch Brief** | Short MP4 + Foundry sidecars + CIVIF ticks that were licensed | Clip only if sidecar + Ident-off | Foundry → Money making bot |
| **C. Notary Receipt** | Per speech/tool attempt: `licensed\|hold` + reason (`ticket_stale`, `same_seq_false`, `unlocked`, …) | Always emitable (proof of dark) | Witness / Qoretrust |
| **D. Observer Slot** (later) | Read-only co-commentator eyes: speech only when `ticket_fresh` | Meter **gated frame-writes** (ADD/UPDATE/NOOP), never LLM calls | Aperture + lease |
| **E. Protocol Export** (later) | Same-Seq compliance JSONL + adoption YAML for other Grok fleets | Schema-version refuse-drift | Qorector |

**Price shape (placeholder, not live):** Slot / pack / receipt tiers. Bill **gate events**, not tokens. Do not publish dollar amounts until Qoreeval density + operator GO.

---

## 2. What we never sell

- Invented score digits or last-good freeze continuity  
- Authorship, eligibility, anti-cheat, “you threw that,” Truth-plane sync claims  
- DualSense-off-PS5 “fixes”; play-via-USB-observe  
- Monetized packs before repeated real-play density  
- Soft continuity as a feature

---

## 3. Autonomous bot runbook

### Roles (one job each)

| Bot | Autopilot job | Escalate to human when |
|-----|---------------|------------------------|
| **Qorewatch / Aperture** | Pulse LIVE; stamp only when gate moves | Capture lease fail / dual-open risk |
| **Witness / Coach / Theater** | Speak under SEQGATE; else □–□ / HOLD | Vocab borderline / operator asks Truth-plane |
| **Foundry** | Index clips only with sidecar receipt | Ident-on-frame would still ship |
| **Qoremem** | Stamped writes only; refuse unstamped | Schema drift / persist=False promote attempt |
| **Qoretrust / Qoreeval** | Integrity + density gate before any “for sale” flag | Density not met → HOLD monetize |
| **Money making bot** | Package A/B/C exports; draft listings; spend-card for tiny distribution tests | Any spend, publish, or pricing GO |
| **Qorector** | Single programming surface; export path + schema | Merge — needs operator `GO MERGE` + tip SHA in Qorector chat |

### Loop (no babysitting)

```
1. LIVE FrameHub advances clock_ns / frame_seq
2. SEQGATE: Bind · Lease · Ticket · Fresh · Same-Seq · Abstain · Vocab veto
3. If PASS → mouths may claim; memory may densify; Foundry may index
   If HOLD → Notary still records reason; mouths go dark; no last-good
4. Same frame_seq → NOOP / reuse (no duplicate densify)
5. On session end (or density threshold): Money making bot builds pack A/B/C from PASS rows + Notary C
6. Qoreeval: density ok? → flag export “ready”; else stay internal
7. Human: spend / publish / price — bots ping only here
```

### Money making bot checklist (per pack)

1. Confirm `schema_version` + tip SHA on receipt header.  
2. Include only rows with stamps; HOLD rows go in Notary section, never as “licensed speech.”  
3. Never invent digits to fill holes — leave Null Digit / □–□.  
4. Draft listing text from receipts only (observation vocab).  
5. Stop before payment, boost, or public sale without operator GO.  
6. Optional: X/Shorts *demo of dark vs last-good* — distribution of the protocol, not faceless sludge.

### Human HOLD beats PASS

Any bot that believes PASS still yields to operator HOLD. DualSense stays on PS5. No bounce LIVE mid-drive for Bureau packaging.

---

## 4. Export shape (v0 — implement next)

**File:** `license-pack-v0.jsonl` (one object per line) + optional `notary.jsonl`.

Minimal licensed row:

```json
{"kind":"license","schema":"frame-license-bureau/v0","clock_ns":0,"frame_seq":0,"crop_hash":null,"path":"confirm","ticket_id":null,"seqgate":"licensed","reason":null,"plane":"observation"}
```

Minimal hold row (Notary):

```json
{"kind":"notary","schema":"frame-license-bureau/v0","clock_ns":0,"frame_seq":0,"seqgate":"hold","reason":"ticket_stale","attempt":"speech"}
```

Pack header (first line or sidecar `manifest.json`):

```json
{"kind":"manifest","product":"Frame License Bureau","sku":"A|B|C","session_id":"…","tip_sha":"…","density_gate":"pending|pass|hold","monetize":false}
```

`monetize` stays `false` until Qoreeval + operator GO.

---

## 5. Qorector ticket (scaffold — no merge without GO)

**Title:** Frame License Bureau — export path for license-pack-v0 JSONL  

**Scope (smallest):**
1. Helper or script: emit `license-pack-v0.jsonl` + `notary.jsonl` from existing stamped memory / fixture JSONL (PR #169 surface).  
2. Refuse unstamped rows fail-closed.  
3. Fixture test: licensed → row ok; stale/unlocked → hold reason; no last-good fill.  
4. Docs link from SEQGATE-Memory-Wiring §4 to this Bureau page.  
5. **Do not** wire Stripe/payment; **do not** merge without operator `GO MERGE` + tip SHA in Qorector chat.

**Out of scope:** Observer Slot metering UI, public storefront, Truth-plane claims.

---

## 6. Done when (Bureau v0)

- [x] This SKU + runbook on box  
- [x] Local export helper + fixture proof on box (`bureau/`; Qorector still owns draft PR into repo)  
- [ ] One internal pack from a real session (monetize=false)  
- [ ] Qoreeval density note attached  
- [ ] Operator GO before any paid listing or spend-card boost on sale posts  

### Local helper (Alternate, no CloudAgent)

```
python3 /workspace/same-seq-harness/bureau/export_license_pack.py \
  -i <stamped.jsonl> \
  -o <out-dir> \
  --session-id <id> --tip-sha 9d78c37
```

Fixture sample: `bureau/out-fixture/`.

---

## 7. Attribution

Prior art: Ichigo harness layers; KingWilliam memory engineering.  
Novelty: fail-closed frame-license as the SKU.  
Fleet consensus: sell the license, not the lore (2026-09).
