"""Built glass SPA is preferred when glass/dist exists; else original Deck HTML."""

from __future__ import annotations

from pathlib import Path


def test_glass_dist_is_under_repo_glass():
    from qoresence.deck.server import _glass_dist, _html

    p = _glass_dist()
    assert p.name in ("dist", "glass_spa")
    assert (p / "index.html").is_file()
    body = _html("deck.html")
    assert 'id="root"' in body


def test_html_falls_back_to_deck_files_without_dist(monkeypatch, tmp_path):
    import qoresence.deck.server as deck

    monkeypatch.setattr(deck, "_glass_candidates", lambda: [tmp_path / "missing"])
    body = deck._html("deck.html")
    original = Path(deck.__file__).with_name("deck.html").read_text(encoding="utf-8")
    assert body == original


def test_html_uses_glass_index_when_dist_present(monkeypatch, tmp_path):
    import qoresence.deck.server as deck

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(
        "<!doctype html><div id='root'>glass-spa</div>", encoding="utf-8"
    )
    monkeypatch.setattr(deck, "_glass_candidates", lambda: [dist])
    assert "glass-spa" in deck._html("deck.html")
    assert "glass-spa" in deck._html("overlay.html")
    assert "glass-spa" in deck._html("index.html")
