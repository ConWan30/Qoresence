# Truth feed

Status: **MVP, default OFF.** Not tested live on the laptop yet (see [Gaps](#honest-gaps)).

The truth feed is an append-only, machine-readable stream of game facts that Qoresence
has actually locked. Any AI agent, overlay, OBS browser source or phone can read it and
check it on its own. Each line is one JSON fact. Every fact is hash-chained to the one
before it and, when the `[truth]` extra is installed, signed with a local Ed25519 key.

It is the streaming companion to the per-clip receipts in
[VERIFIED_REEL_PLAN.md](VERIFIED_REEL_PLAN.md) (PR #282). It uses the same canonical JSON,
the same Ed25519 key type, the same `verified` / `unverified` labels and the same
fail-closed rules.

## Honesty rules (fail-closed)

A score fact is written only when **all** of these hold:

1. A `visual_context` bus event has `score_vlm_locked: true` **and** a `confirm_ticket_id`.
2. The ConfirmTicket is on the payload (`details.confirm_ticket`), its id and digits match
   the payload, and `ticket_is_licensed_lock` passes. That means a non-empty crop hash,
   not a 0-0 kickoff board, and observed within the digit max age (8 s).
3. Capture is live: FrameHub has a frame no older than 5 s. This is the same gate the
   OBS bridge (PR #280) uses.
4. The locked pair differs from the previous locked pair. Held locks are deduplicated.

Unlocked, blank, held, stale, unlicensed or mismatched boards produce **no fact**. The
reason is counted under `/health` → `truth_feed.refused`.

- First lock in a session → `score_lock` (baseline).
- A locked increase → `score_change` (with `prev_scores`).
- A locked decrease or reset (new game, correction) → `score_lock` with
  `meta.baseline_reset: true`. It is never a `score_change` (reel plan §7.4).

**Labels.** `verification.level` is `screen+input` only when PLAY-domain DualSense
presses (at least 2 by default) appear in the 15 s before the lock. Those facts are
labelled `verified`. Everything else is `screen_only` and labelled **`unverified`**, with
reasons (`no_play_input_in_window`, `observe_domain_only`, `too_few_play_presses`,
`input_ring_unavailable`). OBSERVE-domain input (laptop USB Edge) never corroborates.
The verifier rejects a `verified` label without `screen+input`.

**Signing.** If signing is unavailable (no `cryptography` installed, key file
group/world-readable, or unreadable key), the feed writes an unsigned hash chain and
every line says `signed: false`. If a signature fails mid-session, the fact is dropped.
The feed never writes a line that looks signed but is not.

## Enable

```bash
pip install -e ".[deck,truth]"     # [truth] = cryptography (optional; without it: unsigned chain)
qoresence --play --truth-feed      # or QORESENCE_TRUTH_FEED=1
```

| Flag / env | Meaning |
|---|---|
| `--truth-feed` / `QORESENCE_TRUTH_FEED=1` | turn the feed on (default OFF; `--play` does not enable it) |
| `--truth-feed-dir DIR` / `QORESENCE_TRUTH_DIR` | output directory (default `logs/truth`) |
| `--truth-feed-unsigned` / `QORESENCE_TRUTH_SIGN=0` | unsigned hash chain, no key file |
| `QORESENCE_TRUTH_KEY` | key path (default `~/.qoresence/truth_key`) |
| `QORESENCE_TRUTH_INPUT_WINDOW_S` | corroboration window (default 15) |
| `QORESENCE_TRUTH_FEED_LAN=1` | allow non-loopback clients to read `/api/truth/*` |

**Why OFF by default.** Every lobe in `unified_config.py` defaults to OFF, and so do the
other observation-plane add-ons (OBS bridge, OTel, Jev, haptic probe, and the
`--verified-reel` plan). The feed also has side effects a user should opt into: it
writes a new file per session and creates a private key in the home directory. The
runtime cost is small: an enqueue-only subscriber plus one worker thread. Cost is not
the reason it is off.

**Files.**

- `logs/truth/truth_<session_id>.jsonl`: one file per session, append-only. If the
  session restarts with the same key mode, the file is resumed with the chain unbroken.
  If the key mode changed, it moves on to `_2`, `_3`, and so on.
- `~/.qoresence/truth_key`: hex Ed25519 seed, mode 0600, generated on first use.
- `~/.qoresence/truth_key.pub`: hex public key.

The private key is never served, logged or written into a fact.

## Schema (`qoresence.truth.fact.v0`)

| Field | Notes |
|---|---|
| `schema`, `seq`, `session_id` | `seq` starts at 0 and is contiguous |
| `kind` | `session_start` \| `score_lock` \| `score_change` \| `clip_ref` \| `session_end` |
| `clock_ns` | shared monotonic clock (FrameHub/HID). On score facts it is the ticket's `observed_clock_ns` |
| `wall_utc` | informational only, not trusted |
| `game_profile` | e.g. `madden_27`, `cfb_27` |
| `scores` / `prev_scores` | **only** on score facts: `home`, `away`, team abbreviations, `home_left`, `quarter` |
| `frame` | `frame_hash` (the analyzed frame that carried the lock), `lock_crop_hash` (the scorebug crop that minted the ticket), `frame_seq` |
| `source` | `reader` (`local_scorebug` \| `gemini` \| `quicksilver` \| `deepseek`), `plane` (`local` \| `cloud` \| `unknown`), `model`, `ticket_id` |
| `controller` | `null`, or a PLAY-input summary: `play_events`, `play_presses`, `last_input_to_lock_s`, `trace_sha256`, `depth: "presence_only"` |
| `verification` | `{level, label, reasons}`. Session facts use `label: "meta"` |
| `clip` | `clip_ref` only: `file`, `sha256`, `size_bytes`, `duration_s`, `source`, `near_score_seq` |
| `meta` | `session_start`: `pubkey`, `sign_reason`. `session_end`: counts. Resets: `baseline_reset` |
| `prev_hash` | `hash` of the previous line (genesis = 64 zeros) |
| `signed`, `key_id` | `key_id = sha256(pubkey)[:16]`, `null` when unsigned |
| `hash` | sha256 of the canonical body, which excludes `hash` and `signature` |
| `signature` | `{alg: "ed25519", key_id, sig}` over the same canonical bytes, or `null` |

Canonical JSON is `json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)`,
the same as `clock_notary/envelope._canonical` and the reel receipt. `signed` and `key_id`
are inside the hashed body. Stripping a signature therefore breaks the chain.

Example (`score_change`, signed, corroborated):

```json
{
  "schema": "qoresence.truth.fact.v0",
  "seq": 2,
  "session_id": "demo",
  "kind": "score_change",
  "clock_ns": 754174288599131,
  "wall_utc": "2026-10-12T04:22:30.042Z",
  "game_profile": "madden_27",
  "scores": {"home": 14, "away": 3, "home_team": "KC", "away_team": "BUF", "home_left": null, "quarter": null},
  "prev_scores": {"home": 7, "away": 3},
  "frame": {"frame_hash": "ffffffffffffffff", "lock_crop_hash": "c0ffee", "frame_seq": 42,
            "hash_note": "frame_hash=analyzed frame carrying the lock; lock_crop_hash=scorebug crop that minted the ticket"},
  "source": {"reader": "local_scorebug", "plane": "local", "model": "local_scorebug_v1",
             "ticket_id": "a1b2c3d4e5f60718", "bus_session_id": "bus-s"},
  "controller": {"domain": "play", "window_s": 15.0, "play_events": 2, "play_presses": 2,
                 "other_domain_events": 0, "last_input_to_lock_s": 2.001,
                 "trace_sha256": "1b85cac2…", "depth": "presence_only"},
  "verification": {"level": "screen+input", "label": "verified", "reasons": []},
  "clip": null,
  "meta": null,
  "prev_hash": "71551b98…",
  "signed": true,
  "key_id": "f686c659526ab132",
  "hash": "7ae86ba5…",
  "signature": {"alg": "ed25519", "key_id": "f686c659526ab132", "sig": "5316009f…"}
}
```

Without controller input, the same fact has `"controller": null` and
`"verification": {"level": "screen_only", "label": "unverified", "reasons": ["no_play_input_in_window"]}`.

## Deck endpoints (read-only)

All four endpoints are served on the Deck (`127.0.0.1:8765`) by both the FastAPI and the
stdlib servers. They return `503 {"error": "truth_feed_off"}` when the feed is off.

- Only loopback clients are allowed unless `QORESENCE_TRUTH_FEED_LAN=1`.
- The Agent Glass bearer token (`require_token`) applies on top, the same as `/api/observations`.

| Endpoint | Returns |
|---|---|
| `GET /api/truth/feed?since=<seq>&limit=<n>` | recent facts (≤500, newest last) and `next_seq` |
| `GET /api/truth/stream?since=<seq>&limit_s=<s>` | `text/event-stream`. Each fact is `id: <seq>` / `event: fact` / `data: <json>`. Honors `Last-Event-ID`. Sends a `: ping` every 15 s. Ends after `limit_s` (max 3600) |
| `GET /api/truth/verify` | full re-verification of the session file: `ok`, `count`, `signed`, `signatures_checked`, `pubkey`, `head_hash`, `complete`, `errors` |
| `GET /api/truth/pubkey` | `signed`, `alg`, `pubkey` (hex), `key_id`, `sign_reason` |

`/health` gains a `truth_feed` block (path, signed, facts, refused counts, drops) only
when the feed is on.

```bash
curl -s localhost:8765/api/truth/feed | jq '.facts[-1]'
curl -s "localhost:8765/api/truth/feed?since=10" | jq '.facts[] | {seq, kind, scores, verification}'
curl -N localhost:8765/api/truth/stream
curl -s localhost:8765/api/truth/verify | jq '{ok, count, signed, signatures_checked, pubkey}'
curl -s localhost:8765/api/truth/pubkey
```

## Offline verification

```bash
python scripts/verify_truth_feed.py logs/truth/truth_<session>.jsonl
python scripts/verify_truth_feed.py feed.jsonl --pubkey "$(cat ~/.qoresence/truth_key.pub)" --json
```

The script is standalone: it needs only the stdlib, plus `cryptography` for signatures,
and does not import `qoresence`. It checks hashes, `seq` contiguity, `prev_hash` links,
signed/unsigned consistency and signatures. It also checks the honesty structure: digits
only on score facts that cite a ticket, and `verified` only with `screen+input`.

- Exit codes: `0` ok, `1` failed, `2` unreadable.
- Without `--pubkey`, it trusts the key published in the file's `session_start` fact.
  Pin the key for real verification.
- A truncated tail cannot be detected from the file alone. `complete` tells you whether
  the file ends in `session_end`.

## Consumers

- **Grok / any AI agent:** poll `/api/truth/feed?since=<last seq>` or hold the SSE
  stream. Only state digits that come from a `score_*` fact. Say "unverified" whenever
  the label says so. Facts are small enough to drop straight into a prompt as JSON.
- **OBS:** a Browser Source page using `new EventSource("http://127.0.0.1:8765/api/truth/stream")`
  can paint the latest locked score. It can show a ✓ for `verified` or an "UNVERIFIED"
  tag. The OBS bridge (PR #280) still drives replay buffers directly from `visual_context`.
- **Phones:** on the LAN, start with `QORESENCE_TRUTH_FEED_LAN=1` and the Deck bound to
  the LAN, and use the Agent Glass token. The phone can show the feed and run its own
  verification against a pinned public key.
- **Later:** the Verified Reel receipts (PR #282) can cite `truth` facts by `hash`. A
  Rivalatch knock can lodge a session's final `head_hash`.

## Threading

The feed follows AGENTS.md rules 1, 4 and 5. Its bus subscriber copies a handful of
fields into a bounded drop-oldest deque and sets an Event. That is all it does on the
bus thread. Parsing, InputRing reads, clip hashing, signing and disk writes all run on
the `truth-feed` daemon thread. The feed never emits bus events and never takes a lobe
lock. The clip-export hook (`note_clip_exported`) only enqueues, and does nothing when
the feed is off.

## Honest gaps

- **Not live-tested.** Unit and integration tests use fake `visual_context` events, a
  real `RetinaEventBus`, and FastAPI and stdlib route smoke tests. No laptop / HDMI /
  Madden session has been run yet.
- **Controller corroboration is shallow.** It checks for PLAY-domain presses in the
  window before the lock. It does not yet do the reel plan's menu-burst → snap →
  score-timing analysis (§5) or coupling/IVC. `verified` means "a locked screen read,
  plus PLAY-pad input just before it", not "this human caused this score".
- `frame_hash` is the hash the visual lobe reports for the analyzed frame, which may be
  empty. `lock_crop_hash` is the ConfirmTicket crop hash. Neither is a hash of raw HDMI
  pixels re-taken by the feed.
- `clip_ref` links a clip to the latest score fact by time only (`near_score_seq`). The
  clip's frames are not bound to the lock.
- The signing key is a plain local file (0600). There is no TPM / Windows Hello binding
  and no rotation (reel plan §12).
