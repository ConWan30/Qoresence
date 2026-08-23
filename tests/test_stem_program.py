"""Stem Program-out options — FrameHub is not touched."""

from __future__ import annotations

from qoresence.stem.program import apply_program_window, program_options


def test_program_options_map_display_origin():
    opts = program_options(display_index=1, fullscreen=True, burn_hud=True)
    assert opts.origin_x == 1920
    assert opts.origin_y == 0
    assert opts.fullscreen is True
    assert opts.burn_hud is True


def test_apply_program_window_does_not_need_capture():
    calls: list[tuple] = []

    class _Cv:
        WND_PROP_FULLSCREEN = 0
        WINDOW_FULLSCREEN = 1

        @staticmethod
        def moveWindow(title: str, x: int, y: int) -> None:
            calls.append(("move", title, x, y))

        @staticmethod
        def setWindowProperty(title: str, prop: int, val: int) -> None:
            calls.append(("full", title, prop, val))

    apply_program_window(_Cv, "Stem", program_options(display_index=1))
    assert calls[0] == ("move", "Stem", 1920, 0)
    assert calls[1][0] == "full"


def test_stem_config_defaults_off():
    from qoresence.core import RetinaUnifiedConfig

    cfg = RetinaUnifiedConfig()
    assert cfg.stem.conductor is False
    assert cfg.stem.audio is False
    assert cfg.stem.record is False
    assert cfg.stem.program is False
