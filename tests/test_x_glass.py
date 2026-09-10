"""X Glass — default OFF, create≠post, digit_silent kill-path, no invented tokens."""

from __future__ import annotations

import pathlib

import pytest

from qoresence.x import XGlass, XGlassConfig, get_x_glass, set_x_glass, x_glass_health
from qoresence.x.caption import build_caption, extract_digit_gate


@pytest.fixture(autouse=True)
def _reset_glass(tmp_path: pathlib.Path):
    clips = tmp_path / "clips"
    clips.mkdir()
    set_x_glass(None)
    yield clips
    set_x_glass(None)


def _mp4(clips: pathlib.Path, name: str = "hdmi_clip_20260909_120000.mp4") -> pathlib.Path:
    p = clips / name
    p.write_bytes(b"\x00\x00\x00\x18ftypmp42")  # tiny fake mp4 header
    return p


def test_lobe_default_off():
    from qoresence.core.unified_config import RetinaUnifiedConfig

    c = RetinaUnifiedConfig()
    assert c.x_glass.enabled is False
    assert c.x_glass.grant is False
    g = XGlass(XGlassConfig())
    assert g.health()["enabled"] is False
    assert g.health()["last_reason"] == "lobe_off"
    r = g.create(clip_name="hdmi_clip_x.mp4")
    assert r["ok"] is False
    assert r["error"] == "lobe_off"


def test_cli_help_lists_x_glass():
    src = pathlib.Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "--x-glass" in src
    assert "QORESENCE_X_GLASS" in pathlib.Path("qoresence/core/unified_config.py").read_text(
        encoding="utf-8"
    )
    assert "Not implied by --play" in src or "not implied by --play" in src.lower()


def test_missing_mp4_refuses(tmp_path: pathlib.Path, _reset_glass):
    clips = _reset_glass
    g = XGlass(XGlassConfig(enabled=True, grant=True, clips_dir=str(clips)))
    r = g.create(clip_name="hdmi_clip_missing.mp4")
    assert r["ok"] is False
    assert r["error"] == "no_mp4"


def test_create_does_not_post(tmp_path: pathlib.Path, _reset_glass):
    clips = _reset_glass
    path = _mp4(clips)
    g = XGlass(XGlassConfig(enabled=True, grant=True, clips_dir=str(clips)))
    r = g.create(clip_name=path.name, caption_mode="silent")
    assert r["ok"] is True
    assert r["posted"] is False
    assert r["draft"]["media_url"] == f"/media/clips/{path.name}"
    # post without oauth → oauth_missing (silent skips digit_silent)
    p = g.post(caption_mode="silent")
    assert p["ok"] is False
    assert p["error"] == "oauth_missing"
    assert p.get("detail") == "publisher_stub"


def test_post_requires_create(tmp_path: pathlib.Path, _reset_glass):
    clips = _reset_glass
    g = XGlass(XGlassConfig(enabled=True, grant=True, clips_dir=str(clips)))
    p = g.post(caption_mode="silent")
    assert p["ok"] is False
    assert p["error"] == "create_required"


def test_post_no_grant(tmp_path: pathlib.Path, _reset_glass):
    clips = _reset_glass
    path = _mp4(clips)
    g = XGlass(XGlassConfig(enabled=True, grant=False, clips_dir=str(clips)))
    assert g.create(clip_name=path.name, caption_mode="silent")["ok"] is True
    p = g.post(caption_mode="silent")
    assert p["error"] == "no_grant"


def test_digit_silent_when_ticket_missing():
    cap = build_caption(
        {
            "score_vlm_locked": True,
            "ticket_crop_hash": "abc",
            "crop_hash": "abc",
            "home_score": 14,
            "away_score": 7,
            # no confirm_ticket_id
        },
        caption_mode="auto",
    )
    assert cap["digit_silent"] is True
    assert cap["score_line"] == ""
    assert "14-7" not in cap["caption"]


def test_digit_silent_when_vlm_unlocked():
    cap = build_caption(
        {
            "confirm_ticket_id": "t1",
            "score_vlm_locked": False,
            "ticket_crop_hash": "abc",
            "video": {"crop_hash": "abc"},
            "home_score": 21,
            "away_score": 10,
        },
        caption_mode="auto",
    )
    assert cap["digit_silent"] is True
    assert "21-10" not in cap["caption"]


def test_digit_silent_when_crop_stale():
    cap = build_caption(
        {
            "confirm_ticket_id": "t1",
            "score_vlm_locked": True,
            "ticket_crop_hash": "aaa",
            "video": {"crop_hash": "bbb"},
            "home_score": 3,
            "away_score": 0,
        },
        caption_mode="auto",
    )
    assert cap["digit_silent"] is True
    assert cap["gate"]["void_reason"] == "crop_mismatch"


def test_board_locked_alone_does_not_license_digits():
    """Qorex kill-path: board_locked / scoreboard_locked are NOT digit permission."""
    cap = build_caption(
        {
            "board_locked": True,
            "scoreboard_locked": True,
            "home_score": 28,
            "away_score": 24,
            # missing ConfirmTicket + score_vlm_locked + fresh crop
        },
        caption_mode="auto",
    )
    assert cap["digit_silent"] is True
    assert cap["score_line"] == ""
    assert "28-24" not in cap["caption"]
    gate = extract_digit_gate(
        {"board_locked": True, "scoreboard_locked": True, "home_score": 1, "away_score": 0}
    )
    assert gate["licensed"] is False
    assert gate["digit_silent"] is True


def test_licensed_digits_when_all_gates_hold():
    cap = build_caption(
        {
            "confirm_ticket_id": "ticket-xyz",
            "score_vlm_locked": True,
            "ticket_crop_hash": "crop1",
            "video": {"crop_hash": "crop1"},
            "home_score": 17,
            "away_score": 14,
            "title": "Madden",
        },
        caption_mode="auto",
    )
    assert cap["digit_silent"] is False
    assert cap["score_line"] == "17-14"
    assert "17-14" in cap["caption"]
    assert "http" not in cap["caption"].lower()


def test_post_auto_refuses_digit_silent(tmp_path: pathlib.Path, _reset_glass):
    clips = _reset_glass
    path = _mp4(clips)
    g = XGlass(XGlassConfig(enabled=True, grant=True, clips_dir=str(clips)))
    assert g.create(
        clip_name=path.name,
        caption_mode="auto",
        situation={"board_locked": True, "home_score": 7, "away_score": 0},
    )["ok"] is True
    assert g.health()["last_reason"] == "digit_silent"
    p = g.post(
        caption_mode="auto",
        situation={"board_locked": True, "home_score": 7, "away_score": 0},
    )
    assert p["ok"] is False
    assert p["error"] == "digit_silent"


def test_caption_rejects_url_smuggling():
    cap = build_caption(
        {
            "confirm_ticket_id": "t",
            "score_vlm_locked": True,
            "ticket_crop_hash": "c",
            "video": {"crop_hash": "c"},
            "home_score": 1,
            "away_score": 2,
            "title": "see https://x.com/foo",
        },
        caption_mode="auto",
    )
    assert "https://" not in cap["caption"].lower()
    assert "x.com/" not in cap["caption"].lower()


def test_health_snapshot_shape(tmp_path: pathlib.Path, _reset_glass):
    set_x_glass(XGlass(XGlassConfig(enabled=False)))
    h = x_glass_health()
    assert set(h) >= {"enabled", "grant", "ready", "last_reason"}
    assert h["enabled"] is False
    assert get_x_glass().snapshot_field()["enabled"] is False


def test_deck_routes_exist():
    src = pathlib.Path("qoresence/deck/server.py").read_text(encoding="utf-8")
    assert '/api/x-glass"' in src or "/api/x-glass'" in src or '@app.get("/api/x-glass")' in src
    assert "/api/x-glass/create" in src
    assert "/api/x-glass/post" in src
    assert 'body["x_glass"]' in src
