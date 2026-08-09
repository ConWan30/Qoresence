import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8765
INTERVAL_S = 10
AGE_WARN = 1.0
AGE_CRITICAL = 3.0
STALL_PUSH_WINDOW = 30  # pushes must increase within this many seconds

LOG_DIR = Path("logs/pilot")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
LOG_PATH = LOG_DIR / f"soak_{STAMP}.jsonl"


def get_json(url: str) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> None:
    print(f"Soak logger started: {LOG_PATH}", flush=True)
    prev_pushes = None
    prev_push_t = None
    sample_n = 0
    while True:
        t0 = time.monotonic()
        try:
            health = get_json(f"http://{HOST}:{PORT}/health")
            situation = get_json(f"http://{HOST}:{PORT}/api/situation")
        except Exception as e:
            record = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "sample": sample_n,
                "error": str(e),
            }
            with LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            print(f"[{sample_n}] ERROR: {e}", flush=True)
            time.sleep(INTERVAL_S)
            sample_n += 1
            continue

        v = health.get("state", {}).get("video", {})
        pushes = v.get("pushes", 0)
        age = v.get("age_s")
        has_frame = v.get("has_frame", False)
        frames = v.get("frames", 0)
        width = v.get("width", 0)
        height = v.get("height", 0)

        warnings: list[str] = []
        if not has_frame:
            warnings.append("no_frame")
        if age is not None and age > AGE_WARN:
            warnings.append(f"age_warn:{age:.3f}")
        if age is not None and age > AGE_CRITICAL:
            warnings.append(f"age_critical:{age:.3f}")

        push_stalled = False
        if prev_pushes is not None and prev_push_t is not None:
            if pushes == prev_pushes and (time.monotonic() - prev_push_t) > STALL_PUSH_WINDOW:
                push_stalled = True
                warnings.append(f"push_stalled:{pushes}")
        if prev_pushes is None or pushes != prev_pushes:
            prev_pushes = pushes
            prev_push_t = time.monotonic()

        sit = situation.get("situation", {})
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "sample": sample_n,
            "age_s": age,
            "has_frame": has_frame,
            "frames": frames,
            "pushes": pushes,
            "width": width,
            "height": height,
            "fps": health.get("state", {}).get("fps"),
            "game_state": sit.get("game_state"),
            "home_score": sit.get("home_score"),
            "away_score": sit.get("away_score"),
            "quarter": sit.get("quarter"),
            "warnings": warnings,
            "push_stalled": push_stalled,
        }
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        status = "OK" if not warnings else f"WARN:{','.join(warnings)}"
        print(
            f"[{sample_n}] {status} age={age}s frames={frames} pushes={pushes} "
            f"res={width}x{height} state={sit.get('game_state')} score={sit.get('home_score')}-{sit.get('away_score')}",
            flush=True,
        )

        sample_n += 1
        elapsed = time.monotonic() - t0
        time.sleep(max(0.0, INTERVAL_S - elapsed))


if __name__ == "__main__":
    main()
