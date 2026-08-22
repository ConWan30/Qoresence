"""Heavy-module size/shape gate (clutchbot / moment_scorer)."""

from __future__ import annotations

import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_heavy_modules_passes():
    script = ROOT / "scripts" / "check_heavy_modules.py"
    assert script.is_file()
    ns = runpy.run_path(str(script), run_name="not_main")
    assert ns["main"]() == 0
