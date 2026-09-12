"""Observations glass — Sight Glass chrome + JSON API."""

from __future__ import annotations

from pathlib import Path

DECK = Path(__file__).resolve().parents[1] / "qoresence" / "deck"


def test_observations_html_is_aperture_glass():
    html = (DECK / "observations.html").read_text(encoding="utf-8")
    assert "Instrument Sans" in html
    assert "IBM Plex Mono" in html
    assert "--aperture" in html
    assert 'href="/deck.html"' in html
    assert "Accept:'application/json'" in html.replace(" ", "") or 'Accept: "application/json"' in html or "application/json" in html


def test_cli_has_observations_flag():
    text = (Path(__file__).resolve().parents[1] / "qoresence" / "cli.py").read_text(encoding="utf-8")
    assert "--observations" in text
    assert "QORESENCE_OBSERVATIONS" in text
