"""Layout guard for Qoresence Pages: nothing clipped, covered, or overlapping.

Static checks always run. The headless sweep runs when Playwright and a
Chrome/Chromium binary are available (skipped otherwise, e.g. in slim CI):
it serves docs/ locally and, at 390 / 768 / 1024 / 1280 px, fails on
 - text from two different elements overlapping,
 - text cut by an overflow box (code blocks, stat cards, timeline bars),
 - a Copy button sitting over its command,
 - a sideways scrollbar inside a code block (or anywhere at >= 900px),
 - the page itself scrolling sideways.
The animated hero stages are skipped; below 900px the trace timeline and
spans table scroll sideways on purpose.

Front door: the home page opens with a plain-language opener (who it is for,
what you need, what it does, Install + feedback buttons) above the hero, every
Qoresence page links the feedback Discussion in its footer, and no page scrolls
sideways at 375 / 768 / 1024 / 1440 px.
"""
from __future__ import annotations

import functools
import http.server
import re
import shutil
import socketserver
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CSS = (DOCS / "aperture.css").read_text(encoding="utf-8")
PAGES = ["index.html", "watch.html", "install.html", "limits.html", "trace.html",
         "trace.html?demo=1", "dark.html", "rivalatch.html"]
WIDTHS = [390, 768, 1024, 1280]
OVERFLOW_WIDTHS = [375, 768, 1024, 1440]
FEEDBACK = "https://github.com/ConWan30/Qoresence/discussions/269"
# Rivalatch is moving to its own project; its page is left untouched here.
QORESENCE_PAGES = sorted(p for p in DOCS.glob("*.html") if p.name != "rivalatch.html")
# Internal names that must not reach a first-time visitor without a plain gloss.
INTERNAL_TERMS = ("FrameHub", "ConfirmTicket", "glass", "lobe", "DShow", "score_vlm_locked", "InputRing")


def _rule(selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*{([^}]*)}", CSS)
    assert m, selector
    return m.group(1)


def test_code_blocks_wrap_and_reserve_room_for_copy():
    code = _rule(".code")
    assert "white-space: pre-wrap" in code
    assert "overflow-wrap: anywhere" in code
    assert "white-space: pre;" not in code
    copy = _rule(".code .copy")
    assert "float: right" in copy and "position: absolute" not in copy


def test_copy_button_comes_first_in_every_code_block():
    for page in DOCS.glob("*.html"):
        html = page.read_text(encoding="utf-8")
        for m in re.finditer(r'<div class="code"[^>]*>(.*?)</div>', html, re.S):
            body = m.group(1)
            if "data-copy" in body:
                assert body.lstrip().startswith('<button class="copy"'), (page.name, body[:60])


def test_anchor_targets_clear_the_sticky_header():
    assert re.search(r"(?m)^html\s*{[^}]*scroll-padding-top:\s*\d+px", CSS)
    js = (DOCS / "site.js").read_text(encoding="utf-8")
    assert "scrollPaddingTop" in js


def test_trace_stats_cannot_spill_into_neighbours():
    assert "min-width: 0" in _rule(".stat")
    assert "overflow-wrap: anywhere" in _rule(".stat b")
    assert "repeat(3, minmax(0, 1fr))" in _rule(".summary")


def _opener(html: str) -> str:
    m = re.search(r'<section class="wrap q-opener"[^>]*>(.*?)</section>', html, re.S)
    assert m, "home page has no plain-language opener"
    return m.group(1)


def test_home_opens_with_a_plain_language_opener_above_the_hero():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    opener = _opener(html)
    main = html.index('<main id="top">')
    assert main < html.index('class="wrap q-opener"') < html.index('class="wrap q-hero"')
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", opener))
    # who it's for
    for word in ("PS5", "Madden", "College Football", "capture card", "Windows laptop"):
        assert word in text, word
    # what you need
    for word in ("capture card", "Windows", "OBS", "Browser Source", "Optional", "DualSense"):
        assert word in text, word
    # what it does, in one sentence
    assert re.search(r"reads your capture card and shows the score on your stream overlay only when it can confirm it; "
                     r"otherwise the overlay stays blank instead of showing a wrong score\.", text)
    # two buttons: Install first, then the feedback Discussion
    buttons = re.findall(r'<a class="button[^"]*" href="([^"]+)">([^<]+)</a>', opener)
    assert buttons == [("./install.html", "Install"), (FEEDBACK, "Tell me what broke")], buttons
    # the opener is the page's h1; the hero keeps its line below it
    assert re.search(r"<h1 [^>]*>", opener) and html.count("<h1") == 1
    assert "Goes dark instead of lying." in html and 'data-hold-stage' in html
    # no internal jargon in the opener
    for term in INTERNAL_TERMS:
        assert term.lower() not in text.lower(), term


def test_hero_glosses_internal_terms():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    hero = re.search(r'<section class="wrap q-hero"[^>]*>(.*?)</section>', html, re.S).group(1)
    lede = re.search(r'<p class="lede">(.*?)</p>', hero, re.S).group(1)
    assert "ConfirmTicket" not in lede or "confirm check" in lede
    for term in ("FrameHub", "InputRing", "DShow", "score_vlm_locked"):
        assert term not in hero, term
    js = (DOCS / "site.js").read_text(encoding="utf-8")
    hold = js[js.index("Hold loop (home)"):js.index("var TONE_VAR")]
    for term in ("FrameHub", "InputRing", "DShow", "ConfirmTicket"):
        assert term not in hold, term


@pytest.mark.parametrize("page", QORESENCE_PAGES, ids=lambda p: p.name)
def test_every_page_links_the_feedback_discussion_in_its_footer(page: Path):
    html = page.read_text(encoding="utf-8")
    footer = re.search(r'<footer class="site-footer">(.*?)</footer>', html, re.S)
    assert footer, page.name
    assert f'href="{FEEDBACK}">Tell me what broke</a>' in footer.group(1), page.name


def test_install_explains_execution_policy_bypass_honestly():
    html = (DOCS / "install.html").read_text(encoding="utf-8")
    note = re.search(r'<p class="step-note">(.*?)</p>', html, re.S)
    assert note and "-ExecutionPolicy Bypass" in note.group(1)
    assert "does not change your system" in note.group(1)
    # The note is only true while the bundled script never touches the policy itself.
    script = (ROOT / "installer" / "windows" / "Install-Qoresence.ps1").read_text(encoding="utf-8")
    assert "Set-ExecutionPolicy" not in script


PROBE = r"""
() => {
  const skip = e => e.closest('.q-stage, .holo-header, [hidden], script, style, noscript, video') || (e.closest('details:not([open])') && !e.closest('summary'));
  const vis = e => { const s = getComputedStyle(e); return s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05; };
  const runs = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.nodeValue.trim()) continue;
    const el = n.parentElement;
    if (!el || skip(el) || !vis(el)) continue;
    const r = document.createRange(); r.selectNodeContents(n);
    for (const b of r.getClientRects()) {
      if (b.width < 1 || b.height < 1) continue;
      runs.push({ el, b: { l: b.left + scrollX, t: b.top + scrollY, r: b.right + scrollX, btm: b.bottom + scrollY }, text: n.nodeValue.trim().slice(0, 40) });
    }
  }
  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).join('.') : '');
  const out = { text_overlap: [], clipped: [], hscroll: [], copy_cover: [], page_overflow: 0 };
  // pairwise text overlap (different elements, neither contains the other)
  for (let i = 0; i < runs.length; i++) for (let j = i + 1; j < runs.length; j++) {
    const a = runs[i], b = runs[j];
    if (a.el === b.el || a.el.contains(b.el) || b.el.contains(a.el)) continue;
    const w = Math.min(a.b.r, b.b.r) - Math.max(a.b.l, b.b.l), h = Math.min(a.b.btm, b.b.btm) - Math.max(a.b.t, b.b.t);
    if (w > 2 && h > 2) out.text_overlap.push([name(a.el) + ' "' + a.text + '"', name(b.el) + ' "' + b.text + '"']);
  }
  // clipping by overflow ancestors
  for (const run of runs) {
    let p = run.el;
    while (p && p !== document.body) {
      const s = getComputedStyle(p);
      const scroller = p.matches('.timeline, .trace-scroll, .detail pre') && innerWidth < 900;
      if (!scroller && /(hidden|clip|auto|scroll)/.test(s.overflowX + s.overflowY)) {
        const pr = p.getBoundingClientRect(); const L = pr.left + scrollX, R = pr.right + scrollX, T = pr.top + scrollY, B = pr.bottom + scrollY;
        if (run.b.r > R + 1 || run.b.l < L - 1 || run.b.btm > B + 1 || run.b.t < T - 1) { out.clipped.push(name(p) + ' cuts ' + name(run.el) + ' "' + run.text + '"'); break; }
      }
      p = p.parentElement;
    }
  }
  for (const e of document.querySelectorAll('body *')) {
    if (skip(e) || !vis(e)) continue;
    const s = getComputedStyle(e);
    const intended = e.matches('.timeline, .trace-scroll') && innerWidth < 900;  // phone/tablet: data tables scroll on purpose
    if (!intended && /(auto|scroll)/.test(s.overflowX) && e.scrollWidth > e.clientWidth + 1) out.hscroll.push(name(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
  }
  for (const btn of document.querySelectorAll('.code .copy')) {
    const code = btn.parentElement; const br = btn.getBoundingClientRect();
    for (const t of code.childNodes) {
      if (t.nodeType !== 3 || !t.nodeValue.trim()) continue;
      const r = document.createRange(); r.selectNodeContents(t);
      for (const b of r.getClientRects()) {
        if (Math.min(b.right, br.right) - Math.max(b.left, br.left) > 1 && Math.min(b.bottom, br.bottom) - Math.max(b.top, br.top) > 1) { out.copy_cover.push(code.textContent.trim().slice(0, 50)); break; }
      }
    }
  }
  out.page_overflow = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth;
  for (const k of ['text_overlap', 'clipped', 'hscroll', 'copy_cover']) out[k] = [...new Set(out[k].map(x => JSON.stringify(x)))].map(x => JSON.parse(x));
  return out;
}
"""


def _chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


@pytest.fixture(scope="module")
def served_docs():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DOCS))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as httpd:
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
        httpd.shutdown()


@pytest.mark.timeout(900)
def test_headless_no_clipped_or_covered_text(served_docs):
    sync_api = pytest.importorskip("playwright.sync_api")
    chrome = _chrome()
    if not chrome:
        pytest.skip("no Chrome/Chromium binary")
    problems = {}
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome)
        for page in PAGES:
            for width in WIDTHS:
                ctx = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                pg = ctx.new_page()
                pg.goto(f"{served_docs}/{page}", wait_until="load")
                pg.wait_for_timeout(600)
                found = {k: v for k, v in pg.evaluate(PROBE).items() if v}
                if found:
                    problems[f"{page}@{width}"] = found
                ctx.close()
        browser.close()
    assert not problems, problems


@pytest.mark.timeout(600)
def test_headless_no_sideways_scroll_and_opener_on_first_screen(served_docs):
    """375 / 768 / 1024 / 1440: no page scrolls sideways; the opener and both buttons sit in the first screen."""
    sync_api = pytest.importorskip("playwright.sync_api")
    chrome = _chrome()
    if not chrome:
        pytest.skip("no Chrome/Chromium binary")
    problems = {}
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=chrome)
        for page in PAGES:
            for width in OVERFLOW_WIDTHS:
                ctx = browser.new_context(viewport={"width": width, "height": 900}, reduced_motion="reduce")
                pg = ctx.new_page()
                pg.goto(f"{served_docs}/{page}", wait_until="load")
                pg.wait_for_timeout(300)
                over = pg.evaluate("Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth")
                if over > 0:
                    problems[f"{page}@{width}"] = f"page scrolls sideways by {over}px"
                if page == "index.html":
                    box = pg.evaluate("""() => {
                      const o = document.querySelector('#start .q-opener-panel');
                      const btns = [...document.querySelectorAll('#start .actions .button')].map(b => b.getBoundingClientRect());
                      const r = o.getBoundingClientRect();
                      return {top: r.top, left: r.left, right: r.right, inner: innerWidth, h: innerHeight,
                              btnBottom: Math.max(...btns.map(b => b.bottom)), btnRight: Math.max(...btns.map(b => b.right))};
                    }""")
                    if box["left"] < 0 or box["right"] > box["inner"] or box["btnRight"] > box["inner"]:
                        problems[f"opener@{width}"] = f"opener spills sideways {box}"
                    if width >= 768 and box["btnBottom"] > box["h"]:
                        problems[f"opener-buttons@{width}"] = f"buttons below the first screen {box}"
                    if box["top"] > box["h"] / 3:
                        problems[f"opener-top@{width}"] = f"opener starts too low {box}"
                ctx.close()
        browser.close()
    assert not problems, problems
