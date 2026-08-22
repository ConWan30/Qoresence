"""Packaged glass_spa is preferred over a stale glass/dist; else Deck HTML."""

from __future__ import annotations

from pathlib import Path


def test_clip_dock_assets_ship_next_to_deck():
    here = Path(__file__).resolve().parents[1] / "qoresence" / "deck"
    assert (here / "clip-dock.js").is_file()
    assert (here / "clip-dock.css").is_file()
    from qoresence.deck.server import _with_clip_dock

    out = _with_clip_dock("<html><body>x</body></html>")
    assert "clip-dock.js" in out
    assert "clip-dock.css" in out


def test_glass_dist_is_under_repo_glass():
    from qoresence.deck.server import _glass_candidates, _glass_dist, _html

    names = [p.name for p in _glass_candidates()]
    assert names[0] == "glass_spa"
    assert "dist" in names
    p = _glass_dist()
    assert p.name == "glass_spa"
    assert (p / "index.html").is_file()
    body = _html("deck.html")
    assert 'id="root"' in body
    assert "clip-dock.js" in body


def test_packaged_spa_wins_over_stale_dist(monkeypatch, tmp_path):
    import qoresence.deck.server as deck

    spa = tmp_path / "glass_spa"
    dist = tmp_path / "dist"
    spa.mkdir()
    dist.mkdir()
    (spa / "index.html").write_text(
        "<!doctype html><div id='root'>packaged-current</div>", encoding="utf-8"
    )
    (dist / "index.html").write_text(
        "<!doctype html><div id='root'>stale-dist</div>", encoding="utf-8"
    )
    monkeypatch.setattr(deck, "_glass_candidates", lambda: [spa, dist])
    body = deck._html("deck.html")
    assert "packaged-current" in body
    assert "stale-dist" not in body


def test_html_falls_back_to_deck_files_without_dist(monkeypatch, tmp_path):
    import qoresence.deck.server as deck

    monkeypatch.setattr(deck, "_glass_candidates", lambda: [tmp_path / "missing"])
    body = deck._html("deck.html")
    original = Path(deck.__file__).with_name("deck.html").read_text(encoding="utf-8")
    assert "btnClip" in original
    assert "clip-dock.js" in body
    assert "btnClip" in body


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
