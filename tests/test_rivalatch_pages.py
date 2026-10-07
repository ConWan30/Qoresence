"""Static checks for the Rivalatch door page on Qoresence Pages (docs/).

No network. Guards the honesty rules from docs/RIVALATCH_MOTION_NOTES.md:
no keys on Pages, demo data labeled, reduced motion honored, local assets
resolve, and the public CTAs stay in place.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
PAGE = DOCS / "rivalatch.html"
CSS = DOCS / "rivalatch-motion.css"
JS = DOCS / "rivalatch-motion.js"
DOOR = "https://vibegate-production.up.railway.app"


class _Refs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.refs.append(value)


def _refs() -> list[str]:
    p = _Refs()
    p.feed(PAGE.read_text(encoding="utf-8"))
    return p.refs


def test_local_refs_resolve():
    missing = []
    for ref in _refs():
        if ref.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        path = ref.split("#", 1)[0].split("?", 1)[0]
        if path and not (DOCS / path).resolve().exists():
            missing.append(ref)
    assert not missing, missing


def test_public_ctas_present():
    refs = set(_refs())
    for path in ("", "/door/", "/MOBILE_KNOCKER.md", "/listing/", "/AGENT.md"):
        assert DOOR + path in refs, path
    assert "./index.html" in refs
    assert "https://github.com/ConWan30/Qoresence" in refs


def test_no_key_values_on_page():
    blob = "\n".join(p.read_text(encoding="utf-8") for p in (PAGE, CSS, JS))
    assert not re.search(r"X-Api-Key\s*:\s*[A-Za-z0-9_\-]{6,}", blob)
    assert not re.search(r"VIBEGATE_API_KEY\s*=", blob)
    assert not re.search(r"\b(sk|ghp|gho|xox[abp])[-_][A-Za-z0-9]{10,}", blob)


def test_demo_is_labeled_and_honest():
    html = PAGE.read_text(encoding="utf-8")
    assert "not live" in html.lower()
    assert "example knocks" in html.lower()
    assert "not a live Ship session" in html
    assert "Spec untouched" in html
    for code in ("202", "200", "409"):
        assert code in html


def test_reduced_motion_honored():
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in css
    assert "prefers-reduced-motion: reduce" in js
    assert "visibilitychange" in js


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_door_loop_beats():
    out = subprocess.run(
        ["node", "-e",
         "const m=require(process.argv[1]);"
         "console.log(JSON.stringify({p:m.PERIOD,k:m.BEATS.map(b=>b.key),"
         "a:[0,2.5,13.9,15.99,16,-0.5].map(m.beatAt),s:m.BEATS[m.SETTLED].key}))",
         str(JS)],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout
    data = json.loads(out)
    assert data["p"] == 16
    assert data["k"] == ["knock", "lodged", "held", "replay", "recalled", "rival", "contested", "return"]
    assert data["a"] == [0, 1, 6, 7, 0, 7]
    assert data["s"] == "contested"
