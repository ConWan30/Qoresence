"""Session watchdog — polls /health and flags stall/deadlock symptoms live.

Run while the operator plays. Prints one line per sample plus WARN/CRITICAL
lines when invariants from AGENTS.md are violated:

  - age_s > 1.0  → WARN (capture lagging)
  - age_s > 3.0  → CRITICAL (likely stall)
  - frames not increasing for 30s while process alive → CRITICAL (deadlock)
  - pushes not increasing for 30s → CRITICAL (streamer wedge)
  - /health unreachable → CRITICAL (Deck server wedged)

Usage:
    python scripts/session_watchdog.py [--interval 10] [--port 8765]
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import UTC, datetime

HOST = "127.0.0.1"
AGE_WARN = 1.0
AGE_CRIT = 3.0
STALL_WINDOW_S = 30


def fetch(url: str) -> dict | None:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  [CRITICAL] /health unreachable: {e}", flush=True)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=10.0)
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()

    base = f"http://{HOST}:{args.port}"
    prev_pushes = None
    last_push_increase = time.monotonic()
    sample = 0

    print(f"=== Qoresence session watchdog started (interval={args.interval}s) ===", flush=True)
    print(f"    Watching: {base}/health", flush=True)
    print(
        f"    WARN age_s > {AGE_WARN}s | CRITICAL age_s > {AGE_CRIT}s | STALL no frames/pushes for {STALL_WINDOW_S}s",
        flush=True,
    )
    print(flush=True)

    while True:
        h = fetch(f"{base}/health")
        now = time.monotonic()
        ts = datetime.now(UTC).strftime("%H:%M:%S")

        if h is None:
            sample += 1
            time.sleep(args.interval)
            continue

        v = h.get("state", {}).get("video", {})
        sit = h.get("state", {}).get("situation", {})
        ctrl = h.get("state", {}).get("controller", {})
        coup = h.get("state", {}).get("coupling", {})
        a2a = h.get("a2a", {})

        frames = v.get("frames", 0)
        pushes = v.get("pushes", 0)
        age_s = v.get("age_s") or 999
        fps = h.get("state", {}).get("fps") or 0
        has_frame = v.get("has_frame", False)
        ctrl_connected = ctrl.get("connected", False)
        phrase = coup.get("phrase", "?")
        coupling = coup.get("coupling", 0.0)
        game_title = sit.get("game_title", "?")
        title_claim = sit.get("title_claim", False)
        score_locked = sit.get("score_vlm_locked", False) or sit.get("scoreboard_locked", False)
        home = sit.get("home_score", 0)
        away = sit.get("away_score", 0)
        quarter = sit.get("quarter", "?")
        a2a_enabled = a2a.get("enabled", False)

        # Track push increases (frames is ring buffer count, not monotonic)
        if prev_pushes is not None and pushes > prev_pushes:
            last_push_increase = now

        push_stall_s = now - last_push_increase

        # Build status line
        flags = []
        if age_s > AGE_CRIT:
            flags.append(f"CRITICAL:age_s={age_s:.1f}")
        elif age_s > AGE_WARN:
            flags.append(f"WARN:age_s={age_s:.1f}")
        if push_stall_s > STALL_WINDOW_S:
            flags.append(f"CRITICAL:pushes_stalled_{push_stall_s:.0f}s")
        if not has_frame:
            flags.append("WARN:no_frame")

        flag_str = " | ".join(flags) if flags else "OK"
        ctrl_str = "CTRL" if ctrl_connected else "no-ctrl"
        lock_str = "LOCK" if score_locked else "no-lock"
        claim_str = "CLAIM" if title_claim else "no-claim"

        print(
            f"[{ts}] #{sample:04d} f={frames} p={pushes} age={age_s:.2f}s "
            f"fps={fps} {ctrl_str} {lock_str} {claim_str} "
            f"Q{quarter} {home}-{away} {game_title} "
            f"phrase={phrase} coup={coupling:.2f} a2a={a2a_enabled} "
            f"| {flag_str}",
            flush=True,
        )

        # Alert lines for critical issues
        if push_stall_s > STALL_WINDOW_S:
            print(
                f"  *** CRITICAL: pushes stopped increasing for {push_stall_s:.0f}s "
                f"(age_s={age_s:.2f}). If process is alive, this is a lock-ordering "
                f"deadlock, NOT the capture card. Check py-spy thread stacks. ***",
                flush=True,
            )

        prev_pushes = pushes
        sample += 1
        elapsed = time.monotonic() - now
        sleep_s = max(args.interval - elapsed, 1.0)
        time.sleep(sleep_s)


if __name__ == "__main__":
    main()
