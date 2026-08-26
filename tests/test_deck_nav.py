"""Deck glasses nav — Session Theater treatment on every operator page."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "qoresence" / "deck"
GLASS_CMD = ROOT / "glass" / "src" / "components" / "theater" / "command-bar.tsx"

GLASS_HREFS = (
    "/",
    "/deck.html",
    "/session.html",
    "/civif.html",
    "/overlay.html",
    "/studio.html",
    "/mobile.html",
)


def _nav_chunk(html: str) -> str:
    start = html.find('class="glass-nav"')
    assert start >= 0, "missing glass-nav"
    end = html.find("</nav>", start)
    assert end > start
    return html[start:end]


def test_session_glass_nav_lists_civif_as_a_glass():
    html = (DECK / "session.html").read_text(encoding="utf-8")
    nav = _nav_chunk(html)
    for href in GLASS_HREFS:
        assert href in nav
    assert 'href="/session.html" aria-current="page"' in nav
    assert "civif-link" not in html


def test_civif_chrome_matches_session_theater_nav():
    html = (DECK / "civif.html").read_text(encoding="utf-8")
    assert "Session Theater" not in html
    assert 'href="/session.css"' in html
    assert "let liveInflight" in html
    assert "if (liveInflight) return" in html
    nav = _nav_chunk(html)
    for href in GLASS_HREFS:
        assert href in nav
    assert 'href="/civif.html" aria-current="page"' in nav


def test_glass_nav_css_has_theater_interaction():
    css = (DECK / "session.css").read_text(encoding="utf-8")
    assert ".glass-nav a:hover" in css
    assert ".glass-nav a:active" in css
    assert ".glass-nav a:focus-visible" in css
    assert ".glass-nav a[aria-current=\"page\"]" in css


def test_theater_command_bar_includes_civif_glass():
    blob = GLASS_CMD.read_text(encoding="utf-8")
    assert "/civif.html" in blob
    assert "offApp" in blob
    assert "glass-nav" in blob
    for href in GLASS_HREFS:
        assert href in blob


def test_fallback_deck_and_studio_use_glass_nav():
    for name, current in (("deck.html", "/deck.html"), ("studio.html", "/studio.html")):
        html = (DECK / name).read_text(encoding="utf-8")
        nav = _nav_chunk(html)
        for href in GLASS_HREFS:
            assert href in nav, f"{name} missing {href}"
        assert f'href="{current}" aria-current="page"' in nav


def test_clip_dock_civif_chip_uses_glass_tone():
    css = (DECK / "clip-dock.css").read_text(encoding="utf-8")
    js = (DECK / "clip-dock.js").read_text(encoding="utf-8")
    assert "/civif.html" in js
    assert "a.civif" in css
    assert "#68d9e8" not in css.split("a.civif")[1].split("}")[0]
    assert "#8ea396" in css
