"""One outbound Quicksilver POST at a time — ClutchFeed / MatchAgent / VLM share the host."""

from __future__ import annotations

import threading
import time

from qoresence.agents.quicksilver_slot import acquire_quicksilver, quicksilver_busy


def test_second_acquire_waits_not_parallel():
    held = threading.Event()
    released = threading.Event()
    order: list[str] = []

    def holder() -> None:
        with acquire_quicksilver(2.0) as ok:
            assert ok is True
            order.append("hold")
            held.set()
            time.sleep(0.25)
        released.set()

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    assert held.wait(1.0)
    assert quicksilver_busy() is True
    t0 = time.monotonic()
    with acquire_quicksilver(2.0) as ok:
        assert ok is True
        order.append("second")
        assert released.is_set()
    assert time.monotonic() - t0 >= 0.2
    t.join(1.0)
    assert order == ["hold", "second"]


def test_acquire_timeout_skips_when_busy():
    gate = threading.Event()

    def holder() -> None:
        with acquire_quicksilver(2.0) as ok:
            assert ok is True
            gate.wait(2.0)

    t = threading.Thread(target=holder, daemon=True)
    t.start()
    time.sleep(0.05)
    with acquire_quicksilver(0.05) as ok:
        assert ok is False
    gate.set()
    t.join(1.0)


def test_chat_timeout_matches_confirm_vision_budget():
    from qoresence.agents.llm_client import LLMConfig

    chat = LLMConfig.from_quicksilver_env(enabled=False)
    vision = LLMConfig.from_scoreboard_vlm()
    assert chat.timeout_s == 14.0
    assert vision.timeout_s == 14.0
