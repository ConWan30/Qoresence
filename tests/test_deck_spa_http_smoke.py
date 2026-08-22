"""HTTP smoke for Deck glass SPA routes."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

ROOT = Path(__file__).resolve().parents[1]


def test_smoke_deck_spa_http_passes():
    script = ROOT / "scripts" / "smoke_deck_spa_http.py"
    assert script.is_file()
    ns = runpy.run_path(str(script), run_name="not_main")
    assert ns["main"]() == 0
