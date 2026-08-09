import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
INTERVAL_S = 30

LOG_DIR = Path("logs/pilot")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
LOG_PATH = LOG_DIR / f"a2a_soak_{STAMP}.jsonl"


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    print(f"A2A soak logger started: {LOG_PATH}", flush=True)
    sample = 0
    prev_bus = None
    while True:
        t0 = time.monotonic()
        try:
            health = get_json(f"http://{HOST}:{PORT}/health")
            timeline = get_json(f"http://{HOST}:{PORT}/api/timeline")
        except Exception as e:
            print(f"[{sample}] ERROR: {e}", flush=True)
            time.sleep(INTERVAL_S)
            sample += 1
            continue

        a2a = health.get("a2a", {})
        bus = a2a.get("bus", {})
        if prev_bus is None:
            prev_bus = bus

        delta_msgs = bus.get("messages", 0) - prev_bus.get("messages", 0)
        delta_commits = bus.get("commits", 0) - prev_bus.get("commits", 0)
        delta_vetos = bus.get("vetos", 0) - prev_bus.get("vetos", 0)
        prev_bus = bus

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sample": sample,
            "enabled": a2a.get("enabled"),
            "last_reason": a2a.get("last_reason"),
            "messages": bus.get("messages"),
            "commits": bus.get("commits"),
            "vetos": bus.get("vetos"),
            "delta_msgs": delta_msgs,
            "delta_commits": delta_commits,
            "delta_vetos": delta_vetos,
            "drive_graph": timeline.get("drive_graph"),
            "active_drive": timeline.get("active_drive"),
            "why_last": timeline.get("why_last"),
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        print(
            f"[{sample}] a2a enabled={record['enabled']} last={record['last_reason']} "
            f"msgs={record['messages']} (+{delta_msgs}) commits={record['commits']} (+{delta_commits}) "
            f"vetos={record['vetos']} (+{delta_vetos})",
            flush=True,
        )
        sample += 1
        elapsed = time.monotonic() - t0
        time.sleep(max(0.0, INTERVAL_S - elapsed))


if __name__ == "__main__":
    main()
