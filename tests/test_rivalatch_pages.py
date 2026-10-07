"""Static checks for Qoresence Pages (docs/*.html), including the Rivalatch door.

No network. Guards the rules from docs/PAGES_REDESIGN_NOTES.md and
docs/RIVALATCH_MOTION_NOTES.md:

- one stylesheet (aperture.css) and one script (site.js) for every page;
- fonts are self-hosted, every @font-face URL exists, licenses ship with them;
- no keys on Pages, demo data labeled, reduced motion honored;
- local assets resolve and the public CTAs stay in place;
- both beat stages (door loop, hold loop) keep their order and settled frame.
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
HOME = DOCS / "index.html"
CSS = DOCS / "aperture.css"
JS = DOCS / "site.js"
FONTS = DOCS / "fonts"
DOOR = "https://vibegate-production.up.railway.app"
PAGES = sorted(DOCS.glob("*.html"))
RETIRED = ("motion.css", "motion.js", "pages-next.css", "rivalatch-motion.css", "rivalatch-motion.js")


class _Refs(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []
        self.styles: list[str] = []
        self.scripts: list[str] = []
        self.inline_style_blocks = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for name in ("href", "src", "poster"):
            if a.get(name):
                self.refs.append(a[name])
        if tag == "link" and (a.get("rel") or "") == "stylesheet":
            self.styles.append(a.get("href") or "")
        if tag == "script" and a.get("src"):
            self.scripts.append(a["src"])
        if tag == "style":
            self.inline_style_blocks += 1


def _parse(path: Path) -> _Refs:
    p = _Refs()
    p.feed(path.read_text(encoding="utf-8"))
    return p


def test_site_has_the_expected_pages():
    names = {p.name for p in PAGES}
    for n in ("index.html", "watch.html", "install.html", "limits.html", "trace.html", "dark.html", "rivalatch.html"):
        assert n in names, n


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_page_shares_one_stylesheet_and_one_script(page: Path):
    p = _parse(page)
    assert p.styles == ["./aperture.css"], p.styles
    assert p.scripts == ["./site.js"], p.scripts
    assert p.inline_style_blocks == 0
    html = page.read_text(encoding="utf-8")
    assert 'data-menu' in html and 'data-nav' in html
    assert 'name="theme-color" content="#05060a"' in html


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_local_refs_resolve(page: Path):
    missing = []
    for ref in _parse(page).refs:
        if ref.startswith(("http://", "https://", "mailto:", "#", "data:")):
            continue
        path = ref.split("#", 1)[0].split("?", 1)[0]
        if path and not (DOCS / path).resolve().exists():
            missing.append(ref)
    assert not missing, missing


def test_retired_assets_are_gone_and_unreferenced():
    for name in RETIRED:
        assert not (DOCS / name).exists(), name
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        for name in RETIRED:
            assert name not in html, (page.name, name)


def test_fonts_are_self_hosted_and_licensed():
    css = CSS.read_text(encoding="utf-8")
    faces = re.findall(r"@font-face\s*{[^}]*}", css)
    assert len(faces) == 5, len(faces)
    urls = re.findall(r"url\(\s*['\"]?([^'\")]+)['\"]?\s*\)", "\n".join(faces))
    assert urls, "no font urls"
    for url in urls:
        assert not url.startswith(("http:", "https:", "//")), url
        assert (DOCS / url).resolve().is_file(), url
    for family in ("Instrument Sans", "IBM Plex Mono"):
        assert family in css
    assert "jsdelivr" not in css and "fonts.googleapis" not in css
    assert (FONTS / "LICENSE-Instrument-Sans.txt").read_text(encoding="utf-8").count("SIL OPEN FONT LICENSE") >= 1
    assert (FONTS / "LICENSE-IBM-Plex-Mono.txt").read_text(encoding="utf-8").count("SIL OPEN FONT LICENSE") >= 1
    # Only weights that ship are requested anywhere.
    for weight in re.findall(r"font-weight:\s*(\d{3})", css):
        assert weight in {"400", "500", "600"}, weight


def test_qoresence_tokens_drive_the_palette():
    css = CSS.read_text(encoding="utf-8")
    for token in ("--bg: #05060a", "--fg: #e8eaf2", "--muted: #8b90a0", "--live: #9be7ff",
                  "--fast: #d7b36a", "--veto: #e07a7a"):
        assert token in css, token
    for status in ("--st-knock", "--st-lodged", "--st-recalled", "--st-held", "--st-contested", "--st-nocrown"):
        assert status + ":" in css, status
    assert "cubic-bezier(0.23, 1, 0.32, 1)" in css


def test_public_ctas_present():
    refs = set(_parse(PAGE).refs)
    for path in ("", "/door/", "/MOBILE_KNOCKER.md", "/listing/", "/AGENT.md"):
        assert DOOR + path in refs, path
    assert "./index.html" in refs
    assert "https://github.com/ConWan30/Qoresence" in refs


def test_home_keeps_its_links_video_and_non_claims():
    html = HOME.read_text(encoding="utf-8")
    refs = set(_parse(HOME).refs)
    for ref in ("./watch.html", "./rivalatch.html", "https://github.com/ConWan30/Qoresence",
                "https://github.com/ConWan30/Qoresence/releases/latest/download/Qoresence-Windows.zip",
                "./assets/deck-live-demo.mp4", "./assets/deck-live-demo.jpg"):
        assert ref in refs, ref
    for line in ("Goes dark instead of lying.", "Board not licensed — this is a page.",
                 "never a fake live feed", "not a live session", "not a second open of the card",
                 'id="watch"', 'id="proof"'):
        assert line in html, line


def test_no_key_values_on_pages():
    blob = "\n".join(p.read_text(encoding="utf-8") for p in (*PAGES, CSS, JS))
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
    home = HOME.read_text(encoding="utf-8")
    assert "Demo · HOLD · not a live session" in home


def test_gate_readout_sits_off_the_tape():
    """The door label lives in the stage head, not inside the bracket over the film strip."""
    for page in (PAGE, HOME):
        html = page.read_text(encoding="utf-8")
        assert 'class="q-stage-head"' in html
        assert "data-gate-readout" in html
        gate = re.search(r'<div class="q-gate"[^>]*>(.*?)</div>', html, re.S)
        assert gate and gate.group(1).strip() == "", page.name


def test_reduced_motion_and_no_js_honored():
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in css
    assert "prefers-reduced-motion: reduce" in js
    assert "visibilitychange" in js
    # Reveal and shutter only hide content once JS has opted in.
    assert "html.q-motion [data-reveal]" in css
    assert not re.search(r"(?m)^\[data-reveal\]\s*{[^}]*opacity:\s*0", css)


def _node(expr: str) -> dict:
    out = subprocess.run(
        ["node", "-e", "const m=require(process.argv[1]);console.log(JSON.stringify(" + expr + "))", str(JS)],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_door_loop_beats():
    data = _node("{p:m.PERIOD,k:m.door.BEATS.map(b=>b.key),"
                 "a:[0,2.5,13.9,15.99,16,-0.5].map(m.beatAt),s:m.door.BEATS[m.door.SETTLED].key}")
    assert data["p"] == 16
    assert data["k"] == ["knock", "lodged", "held", "replay", "recalled", "rival", "contested", "return"]
    assert data["a"] == [0, 1, 6, 7, 0, 7]
    assert data["s"] == "contested"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_hold_loop_beats_carry_no_score():
    data = _node("{k:m.hold.BEATS.map(b=>b.key),s:m.hold.BEATS[m.hold.SETTLED].key,"
                 "raw:JSON.stringify(m.hold.raw)}")
    assert data["k"] == ["open", "capture", "frame", "board", "pad", "ticket", "dark", "return"]
    assert data["s"] == "ticket"
    # The hold loop never paints digits on the board.
    assert not re.search(r"\b\d+\s*[–-]\s*\d+\b", data["raw"])
    assert "not a live session" in data["raw"].lower() or "no score" in data["raw"].lower()
