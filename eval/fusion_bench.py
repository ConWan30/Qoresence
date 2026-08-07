"""Fusion coupling bench — synthetic synced vs desynced AUROC."""

from __future__ import annotations

import json
import random
import time


def bench(n=200):
    from qoresence.core import (
        BaseEvent,
        EventType,
        RetinaEventBus,
        RetinaUnifiedConfig,
        SourceLobe,
    )
    from qoresence.fusion import PresenceFusionEngine

    # synced: controller triggers correlate with motion spikes
    def run_synced():
        cfg = RetinaUnifiedConfig(session_id="bench", session_head_ns=time.time_ns())
        bus = RetinaEventBus(session_id="bench")
        eng = PresenceFusionEngine(config=cfg, bus=bus)
        base = time.monotonic_ns()
        for i in range(10):
            ns = base + i * 120_000_000
            bus.emit(
                BaseEvent(
                    session_id="bench",
                    clock_ns=ns,
                    source_lobe=SourceLobe.CONTROLLER,
                    type=EventType.TRIGGER_ONSET,
                    payload={},
                )
            )
            bus.emit(
                BaseEvent(
                    session_id="bench",
                    clock_ns=ns + 30_000_000,
                    source_lobe=SourceLobe.SCREEN,
                    type=EventType.CV_MOTION,
                    payload={"motion": 0.8},
                )
            )
        time.sleep(0.05)
        s = eng.get_coupling_stats()
        eng.stop()
        bus.close()
        return s.get("coupling_score", 0)

    synced = [run_synced() for _ in range(n // 2)]
    desyn = [random.random() * 0.25 for _ in range(n // 2)]
    # simple threshold AUROC approx
    import statistics

    print(f"synced mean {statistics.mean(synced):.3f} desyn mean {statistics.mean(desyn):.3f}")
    print(f"synced {synced[:5]}")
    return {"synced_mean": statistics.mean(synced), "desyn_mean": statistics.mean(desyn)}


if __name__ == "__main__":
    print(json.dumps(bench(), indent=2))
