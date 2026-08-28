"""HID-by-seq delay line — pad aligned to painted frame by construction.

Qorespan recommended this as the first engine to fix Ghost painting HID[now]
instead of HID aligned to the FrameHub frame at ~6fps HUDDLE.

Video clock = FrameHub clock_ns / hub_seq. HID thread already stamps clock_ns.
On hub_seq++ (FrameHub stamp subscriber, NOT grab / NOT StreamerRuntime._run_loop
/ NOT under lobe _lock), snapshot analog/buttons from InputRing at
t_hub − lag (existing lead 24ms band) into hid_by_seq[seq].

Ghost / IVC / consumers READ hid_by_seq[hub_seq], never HID[now]. Pad equals
the painted frame by construction even at ~6 fps.

Same seq sampled twice = reuse slot. Zero extra grab work.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Default lookback lag for sampling HID (24ms lead from IVC)
DEFAULT_LAG_MS = 24.0
# Keep last N seq samples
DEFAULT_CAPACITY = 128


@dataclass(frozen=True)
class HidSeqSample:
    """One HID snapshot aligned to a video frame seq."""

    hub_seq: int
    hub_clock_ns: int
    hid_clock_ns: int
    lx: float
    ly: float
    r2: float
    l2: float
    buttons: tuple[str, ...]
    hid_domain: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hub_seq": self.hub_seq,
            "hub_clock_ns": self.hub_clock_ns,
            "hid_clock_ns": self.hid_clock_ns,
            "lx": round(self.lx, 3),
            "ly": round(self.ly, 3),
            "r2": round(self.r2, 3),
            "l2": round(self.l2, 3),
            "buttons": list(self.buttons),
            "hid_domain": self.hid_domain,
        }


class HidSeqLine:
    """Video-aligned HID delay line. Thread-safe. Observation plane only."""

    def __init__(
        self,
        *,
        lag_ms: float = DEFAULT_LAG_MS,
        capacity: int = DEFAULT_CAPACITY,
    ) -> None:
        self._lock = threading.Lock()
        self._lag_ms = max(0.0, float(lag_ms))
        self._samples: dict[int, HidSeqSample] = {}
        self._capacity = max(16, int(capacity))
        self._seq_order: list[int] = []  # LRU for eviction

    def snapshot_at_seq(
        self,
        *,
        hub_seq: int,
        hub_clock_ns: int,
        feed_pll: bool = True,
        video_age_s: float | None = None,
    ) -> HidSeqSample | None:
        """Snapshot HID at t_hub - lag_ms and store by hub_seq.

        Called by FrameHub subscriber on each seq++ event. Returns the sample
        for immediate use, and stores it in the delay line for later reads.
        Same seq sampled twice = reuse slot.

        Args:
            hub_seq: FrameHub sequence number
            hub_clock_ns: FrameHub clock_ns at this seq
            feed_pll: If True, feed LagEstimator.observe_phase with seq-edge delta
            video_age_s: Video age in seconds (for PLL stale check)
        """
        try:
            from qoresence.sync.input_ring import get_input_ring

            ring = get_input_ring()
            target_ns = int(hub_clock_ns) - int(self._lag_ms * 1e6)
            pose = ring.pose_at(target_ns, max_age_ms=80.0)
            hold = ring.hold()

            if pose is None:
                # No HID at target time; use hold as fallback
                lx, ly, r2, l2 = 0.0, 0.0, float(hold.r2), float(hold.l2)
                hid_clock = hold.clock_ns
            else:
                lx, ly, r2, l2 = float(pose.lx), float(pose.ly), float(pose.r2), float(pose.l2)
                hid_clock = pose.clock_ns

            # Domain: check recent events for domain tag
            domain = None
            try:
                events = ring.in_window(target_ns - int(50e6), target_ns + int(10e6))
                if events:
                    domain = events[-1].hid_domain
            except Exception:
                domain = None

            sample = HidSeqSample(
                hub_seq=int(hub_seq),
                hub_clock_ns=int(hub_clock_ns),
                hid_clock_ns=int(hid_clock),
                lx=lx,
                ly=ly,
                r2=r2,
                l2=l2,
                buttons=hold.buttons,
                hid_domain=domain,
            )

            with self._lock:
                self._samples[int(hub_seq)] = sample
                if int(hub_seq) not in self._seq_order:
                    self._seq_order.append(int(hub_seq))
                # Evict oldest if over capacity
                while len(self._seq_order) > self._capacity:
                    old_seq = self._seq_order.pop(0)
                    self._samples.pop(old_seq, None)

            # Optional: Feed PLL with seq-edge phase (Goal C)
            if feed_pll and hid_clock > 0:
                try:
                    from qoresence.sync.hid_domain import allow_pll_observe_phase
                    from qoresence.sync.lag_estimator import get_lag_estimator

                    # Only feed PLL from PLAY pad
                    if allow_pll_observe_phase(domain):
                        delta_ms = (int(hub_clock_ns) - int(hid_clock)) / 1e6
                        age_s = float(video_age_s) if video_age_s is not None else 0.0
                        video_stale = age_s > 0.35  # same threshold as IVC
                        get_lag_estimator().observe_phase(delta_ms, video_stale=video_stale)
                except Exception as e:
                    log.debug("PLL observe_phase from seq-edge failed: %s", e)

            return sample
        except Exception as e:
            log.debug("hid_seq_line snapshot failed: %s", e)
            return None

    def get(self, hub_seq: int) -> HidSeqSample | None:
        """Read HID snapshot for a given hub_seq. None if not sampled yet."""
        with self._lock:
            return self._samples.get(int(hub_seq))

    def latest(self) -> HidSeqSample | None:
        """Return the most recent sample (highest seq)."""
        with self._lock:
            if not self._seq_order:
                return None
            latest_seq = self._seq_order[-1]
            return self._samples.get(latest_seq)

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._samples),
                "capacity": self._capacity,
                "lag_ms": self._lag_ms,
                "seqs": sorted(self._seq_order),
            }

    def clear(self) -> None:
        with self._lock:
            self._samples.clear()
            self._seq_order.clear()


# Process-wide singleton (FrameHub subscriber writes; Ghost/IVC read)
_line = HidSeqLine()
_line_lock = threading.Lock()


def get_hid_seq_line() -> HidSeqLine:
    return _line


def snapshot_at_seq(
    *,
    hub_seq: int,
    hub_clock_ns: int,
    feed_pll: bool = True,
    video_age_s: float | None = None,
) -> HidSeqSample | None:
    """Module helper — best-effort snapshot for FrameHub subscriber."""
    try:
        return get_hid_seq_line().snapshot_at_seq(
            hub_seq=hub_seq,
            hub_clock_ns=hub_clock_ns,
            feed_pll=feed_pll,
            video_age_s=video_age_s,
        )
    except Exception:
        return None


def get_sample(hub_seq: int) -> HidSeqSample | None:
    """Module helper — read sample for Ghost / IVC."""
    try:
        return get_hid_seq_line().get(hub_seq)
    except Exception:
        return None


def put_sample(sample: HidSeqSample) -> None:
    """Test helper — inject a seq-aligned HID snapshot without FrameHub."""
    line = get_hid_seq_line()
    seq = int(sample.hub_seq)
    with line._lock:
        line._samples[seq] = sample
        if seq not in line._seq_order:
            line._seq_order.append(seq)
        while len(line._seq_order) > line._capacity:
            old_seq = line._seq_order.pop(0)
            line._samples.pop(old_seq, None)
