"""Structured uncertainty channels — separate trust dimensions, never one confidence blob."""

from __future__ import annotations

from copy import deepcopy

CHANNEL_CAPTURE = "capture_freshness"
CHANNEL_OCR = "ocr_visual_read"
CHANNEL_INPUT = "input_availability"
CHANNEL_CLOCK = "clock_alignment"
CHANNEL_BOUNDARY = "moment_boundary"
CHANNEL_OUTCOME = "outcome_confirmation"

ALL_CHANNELS = (
    CHANNEL_CAPTURE,
    CHANNEL_OCR,
    CHANNEL_INPUT,
    CHANNEL_CLOCK,
    CHANNEL_BOUNDARY,
    CHANNEL_OUTCOME,
)

_STALE_AGE_S = 5.0


def collect_live_signals() -> dict:
    """Best-effort live health reads for channel_inputs freeze. Unknown fields omitted."""
    out: dict = {}
    try:
        from qoresence.vision.clip_buffer import get_clip_buffer

        stats = get_clip_buffer().stats()
        age = stats.get("age_s")
        if age is not None:
            out["video_age_s"] = float(age)
    except Exception:
        pass
    try:
        from qoresence.sync.ivc import get_last_coupling

        coupling = get_last_coupling() or {}
        if coupling.get("frame_seq") is not None:
            out["coupling_frame_seq"] = coupling.get("frame_seq")
        skew = coupling.get("seq_skew")
        if skew is not None:
            out["seq_skew"] = int(skew)
    except Exception:
        pass
    return out


def channel_inputs_from_evidence(event: dict) -> dict:
    """Merge frozen channel_inputs with detector and ticket fields on evidence."""
    inputs = deepcopy(event.get("channel_inputs") or {})
    det = event.get("detector_output")
    if isinstance(det, dict) and det.get("confidence") is not None:
        inputs["visual_confidence"] = det.get("confidence")
    claim = event.get("score_claim")
    if isinstance(claim, dict):
        qual = claim.get("qualification") or {}
        if qual.get("licensed") is True:
            inputs["scoreboard_licensed"] = True
        elif claim:
            inputs["scoreboard_licensed"] = False
    tick = event.get("tick") or {}
    if tick.get("frame_seq") is not None and "coupling_frame_seq" not in inputs:
        inputs["tick_frame_seq"] = tick.get("frame_seq")
    return inputs


def _capture_channel(inputs: dict) -> dict:
    age = inputs.get("video_age_s")
    if age is None:
        return {}
    status = "stale" if float(age) > _STALE_AGE_S else "fresh"
    return {"status": status, "age_s": round(float(age), 3)}


def _ocr_channel(inputs: dict) -> dict:
    conf = inputs.get("visual_confidence")
    if conf is None:
        return {}
    value = float(conf)
    if value >= 0.75:
        status = "readable"
    elif value >= 0.4:
        status = "low_confidence"
    else:
        status = "unreadable"
    return {"status": status, "confidence": round(value, 3)}


def _input_channel(input_availability: str) -> dict:
    return {"status": input_availability}


def _clock_channel(inputs: dict) -> dict:
    skew = inputs.get("seq_skew")
    if skew is None:
        tick_seq = inputs.get("tick_frame_seq")
        coupling_seq = inputs.get("coupling_frame_seq")
        if tick_seq is not None and coupling_seq is not None:
            skew = abs(int(tick_seq) - int(coupling_seq))
        else:
            return {}
    skew = int(skew)
    status = "aligned" if skew <= 1 else "skewed"
    return {"status": status, "seq_skew": skew}


def _boundary_channel(state: str, tags: list[str]) -> dict:
    if "boundary_timeout" in tags:
        return {"status": "timeout"}
    if state in {"provisional", "partial", "confirmed"}:
        return {"status": "closed_inferred"}
    if state == "tracking":
        return {"status": "tracking_inferred"}
    return {"status": "candidate_inferred"}


def _outcome_channel(state: str, licensed: bool | None) -> dict:
    if state == "confirmed" and licensed:
        return {"status": "scoreboard_qualified", "licensed": True}
    if state == "partial":
        return {"status": "qualification_withheld"}
    return {"status": "unassigned"}


def build_uncertainty_channels(
    *,
    input_availability: str,
    state: str,
    uncertainty_tags: list[str],
    channel_inputs: dict,
    scoreboard_licensed: bool | None = None,
) -> dict:
    """Assemble per-channel dicts. Empty channel dict means abstain."""
    licensed = scoreboard_licensed
    if licensed is None and channel_inputs.get("scoreboard_licensed") is not None:
        licensed = bool(channel_inputs["scoreboard_licensed"])
    return {
        CHANNEL_CAPTURE: _capture_channel(channel_inputs),
        CHANNEL_OCR: _ocr_channel(channel_inputs),
        CHANNEL_INPUT: _input_channel(input_availability),
        CHANNEL_CLOCK: _clock_channel(channel_inputs),
        CHANNEL_BOUNDARY: _boundary_channel(state, uncertainty_tags),
        CHANNEL_OUTCOME: _outcome_channel(state, licensed),
    }


def initial_uncertainty_channels(input_availability: str) -> dict:
    return build_uncertainty_channels(
        input_availability=input_availability,
        state="candidate",
        uncertainty_tags=["inferred_visual_boundary", "input_unavailable"],
        channel_inputs={},
        scoreboard_licensed=False,
    )


def refresh_uncertainty_channels(record: dict, event: dict) -> None:
    """Update record uncertainty_channels from frozen evidence inputs."""
    inputs = channel_inputs_from_evidence(event)
    licensed = None
    if record.get("state") == "confirmed" and record.get("claims"):
        licensed = True
    record["uncertainty_channels"] = build_uncertainty_channels(
        input_availability=record.get("input_availability", "not_on_this_host"),
        state=record.get("state", "candidate"),
        uncertainty_tags=list(record.get("uncertainty") or []),
        channel_inputs=inputs,
        scoreboard_licensed=licensed,
    )
