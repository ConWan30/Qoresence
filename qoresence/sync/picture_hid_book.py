"""Picture HID book — seq-keyed tickets from HDMI control legends.

Observation plane only. Parallel to hid_by_seq, never InputRing.
Fail-closed: latest_live(seq) returns only the ticket for that FrameHub seq.
"""

from __future__ import annotations

import threading
from typing import Any

from qoresence.vision.picture_hid_ticket import PictureHidTicket

DEFAULT_CAPACITY = 128


class PictureHidBook:
    """Process-wide map hub_seq → PictureHidTicket."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._lock = threading.Lock()
        self._by_seq: dict[int, PictureHidTicket] = {}
        self._seq_order: list[int] = []
        self._capacity = max(16, int(capacity))

    def put(self, ticket: PictureHidTicket | None) -> PictureHidTicket | None:
        if ticket is None:
            return None
        seq = int(ticket.frame_seq)
        with self._lock:
            self._by_seq[seq] = ticket
            if seq not in self._seq_order:
                self._seq_order.append(seq)
            while len(self._seq_order) > self._capacity:
                old = self._seq_order.pop(0)
                if old != seq:
                    self._by_seq.pop(old, None)
        return ticket

    def get(self, frame_seq: int | None) -> PictureHidTicket | None:
        """Exact seq only. None if missing (fail-closed)."""
        if frame_seq is None:
            return None
        try:
            seq = int(frame_seq)
        except (TypeError, ValueError):
            return None
        with self._lock:
            return self._by_seq.get(seq)

    def latest_live(self, frame_seq: int | None) -> PictureHidTicket | None:
        """Fail-closed: ticket for this seq only — never reuse another frame."""
        return self.get(frame_seq)

    def latest_nearby(
        self,
        frame_seq: int | None,
        *,
        max_age_seq: int = 90,
    ) -> PictureHidTicket | None:
        """HUD legend from sparse VLM: exact seq, else the newest ticket not older than max_age_seq.

        Bind/Ghost still use hid_by_seq exact. This is observation-only so Preplay
        does not vanish for 89 frames between 1.5s scoreboard VLM ticks.
        """
        exact = self.get(frame_seq)
        if exact is not None:
            return exact
        if frame_seq is None:
            return None
        try:
            seq = int(frame_seq)
        except (TypeError, ValueError):
            return None
        window = max(1, int(max_age_seq))
        with self._lock:
            best: PictureHidTicket | None = None
            best_d = window + 1
            for s, ticket in self._by_seq.items():
                d = seq - int(s)
                if 0 <= d <= window and d < best_d:
                    best = ticket
                    best_d = d
            return best

    def clear(self) -> None:
        with self._lock:
            self._by_seq.clear()
            self._seq_order.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "count": len(self._by_seq),
                "capacity": self._capacity,
                "seqs": sorted(self._seq_order),
            }


_book = PictureHidBook()
_book_lock = threading.Lock()


def get_picture_hid_book() -> PictureHidBook:
    return _book


def reset_picture_hid_book() -> None:
    get_picture_hid_book().clear()
