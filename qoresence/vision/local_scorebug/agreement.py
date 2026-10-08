"""Multi-frame agreement for local scorebug locks (the stricter keyless check).

A local reading may only be offered to the mint path after the SAME
(left score, right score, quarter) was read on ``need`` consecutive sampled
frames, spaced at least ``min_interval_ns`` apart and spanning at least
``min_span_ns``. Any blank frame, any different reading, a session change, a
long gap, or a game clock that runs backwards inside the run resets it.

Suspicious jumps (a drop, both sides moving, or a non-football increment from
the last agreed pair, per ``implausible_transition_reason``) are re-read: the
run must reach ``need_suspicious`` samples over ``min_span_suspicious_ns``
before the new pair is offered. This is the local analog of ``ScoreRecheck``:
local reads are cheap, so the re-read is several more frames, not another
cloud call. The mint path still applies every existing refusal afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from qoresence.sync.digit_integrity import implausible_transition_reason
from qoresence.vision.local_scorebug.reader import FrameRead


@dataclass(frozen=True)
class AgreementConfig:
    need: int = 3
    min_interval_ns: int = 200_000_000
    min_span_ns: int = 400_000_000
    max_gap_ns: int = 2_000_000_000
    need_suspicious: int = 9
    min_span_suspicious_ns: int = 2_000_000_000
    # A suspicious-jump judgement only applies against a recent agreed pair.
    jump_memory_ns: int = 30_000_000_000


@dataclass
class _Sample:
    clock_ns: int
    read: FrameRead
    crop_hash: str


@dataclass
class AgreementState:
    key: tuple[int, int, int] | None = None
    session_id: str = ""
    samples: list[_Sample] = field(default_factory=list)


@dataclass(frozen=True)
class AgreementResult:
    agreed: bool
    reason: str
    run: int
    read: FrameRead | None = None
    crop_hash: str = ""
    first_ns: int = 0
    last_ns: int = 0
    suspicious: bool = False


class AgreementWindow:
    """Not thread-safe by itself; the service serialises calls under its lock."""

    def __init__(self, config: AgreementConfig | None = None) -> None:
        self.config = config or AgreementConfig()
        self.state = AgreementState()
        self.last_agreed: tuple[int, int] | None = None
        self.last_agreed_ns = 0
        self.last_agreed_session = ""

    def reset(self) -> None:
        self.state = AgreementState(session_id=self.state.session_id)

    def offer(
        self, read: FrameRead, *, clock_ns: int, crop_hash: str, session_id: str
    ) -> AgreementResult:
        cfg = self.config
        st = self.state
        if session_id != st.session_id:
            self.state = st = AgreementState(session_id=session_id)
            self.last_agreed = None
            self.last_agreed_ns = 0
        if not read.ok or read.pair is None or read.quarter is None:
            self.reset()
            return AgreementResult(False, read.reason or "blank", 0)
        if not str(crop_hash or "").strip():
            self.reset()
            return AgreementResult(False, "empty_crop_hash", 0)
        key = (read.pair[0], read.pair[1], int(read.quarter))
        last = st.samples[-1] if st.samples else None
        restart = (
            st.key != key
            or last is None
            or clock_ns - last.clock_ns > cfg.max_gap_ns
            or clock_ns < last.clock_ns
            or (
                read.clock_seconds is not None
                and last.read.clock_seconds is not None
                and read.clock_seconds > last.read.clock_seconds
            )
        )
        if restart:
            st.key = key
            st.samples = [_Sample(clock_ns, read, crop_hash)]
        elif clock_ns - last.clock_ns >= cfg.min_interval_ns:
            st.samples.append(_Sample(clock_ns, read, crop_hash))
        else:
            # Too close to the previous sample: not new evidence, not a reset.
            pass
        run = len(st.samples)
        first, newest = st.samples[0], st.samples[-1]
        span = newest.clock_ns - first.clock_ns
        suspicious = bool(
            self.last_agreed is not None
            and self.last_agreed != read.pair
            and clock_ns - self.last_agreed_ns <= cfg.jump_memory_ns
            and implausible_transition_reason(*self.last_agreed, *read.pair)
        )
        need = cfg.need_suspicious if suspicious else cfg.need
        need_span = cfg.min_span_suspicious_ns if suspicious else cfg.min_span_ns
        if run < need or span < need_span:
            return AgreementResult(
                False, "recheck" if suspicious else "agreeing", run, suspicious=suspicious
            )
        self.last_agreed = read.pair
        self.last_agreed_ns = newest.clock_ns
        self.last_agreed_session = session_id
        return AgreementResult(
            True,
            "agreed",
            run,
            read=newest.read,
            crop_hash=newest.crop_hash,
            first_ns=first.clock_ns,
            last_ns=newest.clock_ns,
            suspicious=suspicious,
        )
