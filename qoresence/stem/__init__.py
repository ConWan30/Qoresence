"""Retina Stem — situation-directed session stem (not an OBS clone)."""

from .conductor import (
    CLIP_HOLD_MS,
    DirectorBrief,
    DirectorInput,
    StemConductor,
    auto_clip_allowed,
    director_brief,
    director_reasons,
    should_clip,
)
from .program import StemProgramOptions, apply_program_window, program_options
from .resolve import is_capture_card_audio, is_denied_audio, resolve_audio_device
from .runtime import StemRuntime, get_stem_runtime, start_stem, stop_stem

__all__ = [
    "CLIP_HOLD_MS",
    "DirectorBrief",
    "DirectorInput",
    "StemConductor",
    "StemProgramOptions",
    "StemRuntime",
    "apply_program_window",
    "auto_clip_allowed",
    "director_brief",
    "director_reasons",
    "get_stem_runtime",
    "is_capture_card_audio",
    "is_denied_audio",
    "program_options",
    "resolve_audio_device",
    "should_clip",
    "start_stem",
    "stop_stem",
]
