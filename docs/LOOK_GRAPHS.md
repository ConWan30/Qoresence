# Look-license graphs

Observation-plane only. Qoresence is a **Gaming Streaming Observatory Engine**: one capture aperture, one clock, many read-only glasses. These graphs license the **next look** — which crop, frame, ticket, or unit may run. They do not play, narrate, or self-improve.

> DriveGraph remembers what happened. The unit graph decides what may run. The learning edge makes the next DriveGraph cut work from accepted evidence. Look-license graphs decide which look is allowed next.

Flag: `--look-graphs` / `QORESENCE_LOOK_GRAPHS`. Default **OFF**. `--play` does not enable this. When OFF, behavior matches current main: no license read, no license write.

Per-graph dark-ship: `QORESENCE_LOOK_TICKET_DAG`, `QORESENCE_LOOK_CROP`, `QORESENCE_LOOK_SAME_SEQ`, `QORESENCE_LOOK_REFUSE`, `QORESENCE_LOOK_SCALE`, `QORESENCE_LOOK_NEGATIVE` (set `0`/`false`/`off` to disable one graph while the master flag is on).

## Layers

| Layer | Type | Role |
|---|---|---|
| **A — DriveGraph** | attributed temporal causal DAG | What happened this drive. Unchanged. Cap 48 / floor 8 / ceiling 96. |
| **B — Unit graph** | directed control-flow with gates | What may run. |
| **C — Learning edge** | append-only constraint store | What the next splitter may read. |
| **D — LookLicense** | next-look receipt | Which crop / frame / mint / skip is licensed now (`qoresence/graphs/`). |

A LookLicense is not a report and not a score. Digits stay confirm-ticket licensed. Heat stays coupling-ticket licensed.

## Six graphs

| Graph | Licenses | Attach |
|---|---|---|
| Ticket provenance | reuse / remint / refuse | `ConfirmTicketBook` + `board_why` |
| Crop evidence | which existing scorebug band | `scorebug_crops_for_profile` (reorder only) |
| Same-Seq join | which `frame_seq` | `LivePaint` + Ghost Stick + coupling ticket |
| Refuse chain | after a refuse, what to try | `board_why` + `FREEZE_KINDS` |
| Scale stack | which timescale may request a look | CIVIF tick → phrase → drive → session |
| Negative evidence | emptiness as skip/redirect | `NO_CLAIM_REASONS`, blank BGR, `dest_denied` |

## LookLicense record

`LookLicense`: `id`, `clock_ns`, `session_id`, `graph`, `kind`, `permits`, `refuses`, optional `source_ticket_id` / `frame_seq` / `crop_hash`, `plane=qoresence-observation`.

`make_license(...)` returns `None` when the graph/kind is unknown, the payload has score digits, or the write names a frozen field (`qortroller-truth`, wrap dest, score keys, …).

JSONL: `logs/pilot/look_licenses.jsonl` (override `QORESENCE_LOOK_LICENSES_PATH`).

When `--learning-edge` is also on, a LookLicense may mint an existing constraint kind (`crop_band` | `schedule_skip` | `freeze_weight` | `hysteresis`). No new constraint kinds.

## Lock rule

Record after `ConfirmTicketBook` / lobe locks release. Never `emit_raw` from a graph. Never acquire a lobe lock in a subscribe callback.

## Operator

```powershell
# default: identical to main (no look-license I/O)
python -m qoresence.cli --play --deck

# opt-in next-look graphs
python -m qoresence.cli --play --deck --look-graphs
# or: $env:QORESENCE_LOOK_GRAPHS=1

# both flags: licenses may feed existing learning-edge kinds
python -m qoresence.cli --play --deck --look-graphs --learning-edge
```
