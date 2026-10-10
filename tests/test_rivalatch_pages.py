"""Static checks for Qoresence Pages (docs/*.html), including the Rivalatch pointer card.

No network. Guards the rules from docs/PAGES_MOTION_NOTES.md:

- one stylesheet (aperture.css) and one script (site.js) for every page;
- fonts are self-hosted, every @font-face URL exists, licenses ship with them;
- the palette tokens are the ones sampled from the HDMI-Q logo;
- no keys on Pages, demo data labeled, reduced motion and hidden tabs honored;
- local assets resolve and the public CTAs stay in place;
- rivalatch.html stays a short pointer card to the canonical Rivalatch site;
- the home read stage keeps its beat order, settles on LOCKED, and only puts
  digits on the board after three matching reads.
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
    # One header for every page: status strip + wordmark + a nav that is never hidden
    # behind a menu button (phones swipe it as one row).
    assert 'class="holo-header"' in html and 'class="site-hold" role="status"' in html
    assert "data-nav" in html and "data-menu" not in html
    assert 'name="theme-color" content="#010206"' in html


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


LOGO_TOKENS = {"--void": "#010206", "--aqua": "#66e0e6", "--aqua-hi": "#a9fbfd", "--gold": "#fcde74"}


def test_qoresence_tokens_drive_the_palette():
    css = CSS.read_text(encoding="utf-8")
    for name, value in LOGO_TOKENS.items():
        assert f"{name}: {value}" in css, name
    for token in ("--ink: #e4f1f3", "--mute: #8a9ea6", "--blank:"):
        assert token in css, token
    for status in ("--st-signal", "--st-read", "--st-locked", "--st-dark", "--st-recheck"):
        assert status + ":" in css, status
    # Gold is the locked moment only: every gold use sits on a lock selector.
    assert "--st-locked: var(--gold)" in css
    gold_rules = re.findall(r"([^{}]+){([^}]*(?:var\(--gold\)|252, 222, 116)[^}]*)}", css)
    assert len(gold_rules) >= 5
    for rule in gold_rules:
        selector = rule[0].strip().splitlines()[-1]
        assert re.search(r"locked|is-open|q-seal|:root", selector), selector
    assert "cubic-bezier(0.2, 0.7, 0.1, 1)" in css


def test_palette_tokens_match_the_logo():
    """Aqua, aqua-hi and gold must stay close to the logo's own pixels."""
    image = pytest.importorskip("PIL.Image")
    logo = image.open(DOCS / "assets" / "qoresence-logo.png").convert("RGB")
    raw = logo.tobytes()
    px = [tuple(raw[i : i + 3]) for i in range(0, len(raw), 3)]

    def median(pred):
        sel = [p for p in px if pred(p)]
        assert sel
        return tuple(sorted(c[i] for c in sel)[len(sel) // 2] for i in range(3))

    def rgb(hexv):
        return tuple(int(hexv[i : i + 2], 16) for i in (1, 3, 5))

    def near(a, b, tol=24):
        return max(abs(x - y) for x, y in zip(a, b, strict=True)) <= tol

    assert near(rgb(LOGO_TOKENS["--aqua"]), median(lambda p: p[1] > 180 and p[2] > 180 and p[0] < 160))
    assert near(rgb(LOGO_TOKENS["--gold"]), median(lambda p: p[0] > 200 and p[1] > 170 and p[2] < 140))
    assert near(rgb(LOGO_TOKENS["--void"]), median(lambda p: sum(p) < 45), tol=6)


def test_public_ctas_present():
    refs = set(_parse(PAGE).refs)
    for path in ("/", "/listing/"):
        assert DOOR + path in refs, path
    assert "./index.html" in refs
    assert "https://github.com/ConWan30/Qoresence" in refs


def test_rivalatch_page_is_a_pointer_card():
    """Rivalatch has its own site; this URL stays alive as a short card pointing there."""
    html = PAGE.read_text(encoding="utf-8")
    assert html.count("<h1") == 1
    assert 'class="q-pointer"' in html
    assert f'class="button primary" href="{DOOR}/"' in html
    assert f'href="{DOOR}/listing/"' in html
    assert "Rivalatch ship receipt" in html
    assert "Mobile Glass" in html
    # The door loop is gone from Pages: no stage, no example wire, no motion hooks.
    for gone in ("data-door-stage", "q-stage", "data-wire", "data-reveal"):
        assert gone not in html, gone


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_nav_rivalatch_tab_points_at_canonical_site(page: Path):
    html = page.read_text(encoding="utf-8")
    nav = re.search(r"<nav[^>]*data-nav[^>]*>(.*?)</nav>", html, re.S)
    assert nav, page.name
    assert f'<a href="{DOOR}/">Rivalatch</a>' in nav.group(1), page.name
    assert "./rivalatch.html" not in nav.group(1), page.name


def test_home_keeps_its_links_video_and_non_claims():
    html = HOME.read_text(encoding="utf-8")
    refs = set(_parse(HOME).refs)
    for ref in ("./watch.html", "./rivalatch.html", "https://github.com/ConWan30/Qoresence",
                "https://github.com/ConWan30/Qoresence/releases/latest/download/Qoresence-Windows.zip",
                "./assets/deck-live-demo.mp4", "./assets/deck-live-demo.jpg"):
        assert ref in refs, ref
    text = re.sub(r"<[^>]+>", "", html)
    assert "Goes dark instead of lying." in text
    for line in ("Board not licensed — this is a page.",
                 "never a fake live feed", "not a live session", "not a second open of the card",
                 'id="watch"', 'id="proof"'):
        assert line in html, line


def test_no_key_values_on_pages():
    blob = "\n".join(p.read_text(encoding="utf-8") for p in (*PAGES, CSS, JS))
    assert not re.search(r"X-Api-Key\s*:\s*[A-Za-z0-9_\-]{6,}", blob)
    assert not re.search(r"VIBEGATE_API_KEY\s*=", blob)
    assert not re.search(r"\b(sk|ghp|gho|xox[abp])[-_][A-Za-z0-9]{10,}", blob)


def test_demo_is_labeled_and_honest():
    home = HOME.read_text(encoding="utf-8")
    head = re.search(r'<div class="q-stage-head"[^>]*>(.*?)</div>', home, re.S)
    assert head and "Demo · fixture frames · not live" in head.group(1)
    assert "fixture" in re.search(r"<div class=\"q-stage\"[^>]*aria-label=\"([^\"]+)\"", home).group(1)


def test_read_stage_markup_is_the_settled_locked_frame():
    """Without JS (and with reduced motion) the markup already shows LOCKED: open iris, gold board, 3/3."""
    html = HOME.read_text(encoding="utf-8")
    assert html.count("data-read-stage") == 1
    assert 'data-state="locked"' in html
    assert 'class="q-iris is-open" data-iris' in html
    assert 'class="q-board is-locked" data-board' in html
    assert '<span class="q-stamp" data-stamp>3/3</span>' in html
    # Inline SVG aperture: six blades over the HDMI port, nine pins, the gold tick.
    svg = re.search(r'<div class="q-iris[^"]*" data-iris>(.*?)</div>', html, re.S).group(1)
    assert svg.count('class="blade"') == 6 and svg.count('class="blade blade-edge"') == 6
    assert svg.count('class="pin"') == 9 and 'class="port"' in svg and 'class="tick"' in svg


def test_reduced_motion_and_no_js_honored():
    css = CSS.read_text(encoding="utf-8")
    js = JS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion: reduce" in css
    assert "prefers-reduced-motion: reduce" in js
    assert "visibilitychange" in js
    # Reveal and shutter only hide content once JS has opted in.
    assert "html.q-motion [data-reveal]" in css
    assert not re.search(r"(?m)^\[data-reveal\]\s*{[^}]*opacity:\s*0", css)
    # Hidden tabs pause every CSS loop; reduced motion turns them all off.
    assert "html.is-tab-hidden *" in css and "is-tab-hidden" in js
    rm = css[css.index("@media (prefers-reduced-motion: reduce)"):]
    assert "animation: none !important" in rm and "transition: none !important" in rm


def test_motion_is_transform_and_opacity_only():
    css = CSS.read_text(encoding="utf-8")
    blocks = re.findall(r"@keyframes\s+[\w-]+\s*{((?:[^{}]*{[^}]*})*)\s*}", css)
    assert len(blocks) >= 8
    for frames in blocks:
        for prop in re.findall(r"([a-z-]+)\s*:", frames):
            assert prop in {"opacity", "transform"}, prop


def _node(expr: str) -> dict:
    out = subprocess.run(
        ["node", "-e", "const m=require(process.argv[1]);console.log(JSON.stringify(" + expr + "))", str(JS)],
        capture_output=True, text=True, timeout=30, check=True,
    ).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_read_stage_beats():
    data = _node("{p:m.LOOP,k:m.read.BEATS.map(b=>b.key),s:m.read.BEATS[m.read.SETTLED].key,"
                 "a:[0,1500,3800,9000,10500,12800,15999,16000,-1].map(m.beatAt)}")
    assert data["p"] == 16000
    assert data["k"] == ["dark", "read-1", "read-2", "read-3", "locked", "doubt", "recheck",
                         "recheck-1", "recheck-2", "recheck-3", "recheck-4", "reset", "fade"]
    assert data["s"] == "locked"
    assert data["a"] == [0, 1, 4, 5, 6, 11, 12, 0, 12]


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_read_stage_paints_digits_only_after_three_matching_reads():
    beats = _node("m.read.raw")
    seen_board = None
    for beat in beats:
        board = beat.get("board") or seen_board
        seen_board = board
        if not board:
            continue
        if board["score"]:
            # Digits on the board only on the locked beat, after 3 of 3 reads.
            assert board["state"] == "locked", beat["key"]
            assert beat["reads"] == [3, 3], beat["key"]
        if beat["key"] in ("dark", "doubt", "reset") or beat["key"].startswith("recheck"):
            assert board["score"] is None, beat["key"]
            assert board["state"] != "locked", beat["key"]
        if beat["key"].startswith("recheck") and beat.get("reads"):
            assert beat["reads"][1] == 9, beat["key"]
    # The local reader has no template for 8 and no clock of 10:00+: the fixture never shows them.
    raw = json.dumps(beats)
    assert "8" not in re.sub(r'"(t|seq)": \d+', "", raw)
    assert not re.search(r"\b1\d:\d\d\b", raw)
