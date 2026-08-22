"""Land hygiene: shipped glass SPA smoke + size/shape (no network)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_check_glass_spa_script_passes():
    script = ROOT / "scripts" / "check_glass_spa.py"
    assert script.is_file()
    ns = runpy.run_path(str(script), run_name="not_main")
    assert ns["main"]() == 0


def test_glass_spa_or_dist_shape():
    sys.path.insert(0, str(ROOT / "scripts"))
    import check_glass_spa as gate  # type: ignore

    spa = gate.resolve_spa()
    assert spa is not None
    html = (spa / "index.html").read_text(encoding="utf-8")
    js = gate.ASSET_JS.findall(html)
    css = gate.ASSET_CSS.findall(html)
    assert len(js) == 1 and len(css) == 1
    js_path = spa / js[0].lstrip("/")
    css_path = spa / css[0].lstrip("/")
    assert js_path.is_file() and css_path.is_file()
    assert gate.MIN_JS_BYTES <= js_path.stat().st_size <= gate.MAX_JS_BYTES
    assert gate.MIN_CSS_BYTES <= css_path.stat().st_size <= gate.MAX_CSS_BYTES
    blob = js_path.read_text(encoding="utf-8", errors="ignore")
    assert "score_vlm_locked" in blob and "boardLocked" in blob
    assert "hdmiJpegKeep" in blob
