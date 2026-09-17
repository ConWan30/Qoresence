"""Gamer honesty speech — Theater/Now copy, never licenses digits."""

from qoresence.observability.honesty_speech import gamer_honesty_speech


def test_ident_is_blank_over_stale():
    out = gamer_honesty_speech(honesty_band="ok", ident_now=True, enabled=True)
    assert "blank" in out["line"].lower() or "stale" in out["line"].lower()
    assert out["ident"] is True
    assert out["licenses_digits"] is False


def test_off_is_silent():
    out = gamer_honesty_speech(honesty_band="ident", enabled=False)
    assert out["line"] == ""
    assert out["licenses_digits"] is False


def test_presence_not_clutch():
    out = gamer_honesty_speech(presence_token="dense", honesty_band="ok")
    assert "clutch" not in out["presence"].lower()
    assert "highlight" not in out["presence"].lower()
