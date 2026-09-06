"""SEQGATE v0 — Same frame or silence. Fail-closed digit/claim speech."""

from __future__ import annotations

from qoresence.sync.digit_integrity import CONFIRM_DIGIT_MAX_AGE_NS

LICENSED = dict(
    confirm_ticket_id="c-1",
    score_vlm_locked=True,
    path="confirm",
    ticket_crop_hash="crop-a",
    live_crop_hash="crop-a",
    same_seq=True,
    ticket_clock_ns=1_000,
    live_clock_ns=2_000,
    frame_seq=42,
    home_score=14,
    away_score=10,
)


def test_lock_pass_speaks_digits():
    from qoresence.sync.seqgate import NULL_DIGIT, license_digits

    gate = license_digits(**LICENSED)
    assert gate["licensed"] is True
    assert gate["speech"] == "14-10"
    assert gate["speech"] != NULL_DIGIT
    assert gate["reason"] == "licensed"
    assert gate["bind"]["clock_ns"] == 2_000
    assert gate["bind"]["frame_seq"] == 42
    assert gate["bind"]["path"] == "confirm"
    assert gate["bind"]["plane"] == "qoresence-observation"
    assert gate["bind"]["kind"] == "fact"


def test_missing_ticket_is_null_digit_not_last_good():
    from qoresence.sync.seqgate import NULL_DIGIT, license_digits

    gate = license_digits(**{**LICENSED, "confirm_ticket_id": ""})
    assert gate["licensed"] is False
    assert gate["speech"] == NULL_DIGIT
    assert "14" not in gate["speech"]
    assert "10" not in gate["speech"]
    assert gate["reason"] == "no_ticket"
    assert gate["bind"]["kind"] == "hold"
    assert gate["layer"] == "ticket"


def test_stale_ticket_does_not_freeze_last_good():
    from qoresence.sync.seqgate import NULL_DIGIT, license_digits

    gate = license_digits(
        **{
            **LICENSED,
            "ticket_clock_ns": 1,
            "live_clock_ns": 1 + CONFIRM_DIGIT_MAX_AGE_NS + 1,
        }
    )
    assert gate["licensed"] is False
    assert gate["speech"] == NULL_DIGIT
    assert gate["reason"] == "ticket_stale"
    assert gate["layer"] == "fresh"
    assert gate["bind"]["kind"] == "hold"


def test_seq_skew_blanks():
    from qoresence.sync.seqgate import NULL_DIGIT, license_digits

    gate = license_digits(**{**LICENSED, "same_seq": False})
    assert gate["licensed"] is False
    assert gate["speech"] == NULL_DIGIT
    assert gate["reason"] == "seq_skew"
    assert gate["layer"] == "same_seq"


def test_path_fast_never_invents_hard_claims():
    from qoresence.sync.seqgate import NULL_DIGIT, license_digits

    gate = license_digits(**{**LICENSED, "path": "fast"})
    assert gate["licensed"] is False
    assert gate["speech"] == NULL_DIGIT
    assert gate["reason"] == "path_fast"
    assert gate["bind"]["path"] == "fast"
    assert gate["bind"]["kind"] == "veto"
    assert gate["layer"] == "ticket"


def test_vocab_veto_bans_authorship_and_throw_talk():
    from qoresence.sync.seqgate import HOLD, vocab_veto

    assert vocab_veto("presence density rose") is None
    assert vocab_veto("pad–picture coupling") is None
    assert vocab_veto("you threw that") == "vocab_veto"
    assert vocab_veto("anti-cheat flag") == "vocab_veto"
    assert vocab_veto("proof of humanity") == "vocab_veto"
    claim = license_claim_hold("you threw that")
    assert claim["licensed"] is False
    assert claim["speech"] == HOLD
    assert claim["bind"]["kind"] == "veto"
    assert claim["layer"] == "vocab"


def license_claim_hold(text: str):
    from qoresence.sync.seqgate import license_claim

    return license_claim(text, **LICENSED)


def test_lease_layer_uses_existing_capture_lease(tmp_path):
    from qoresence.capture.lease import acquire_capture_lease, release_capture_lease
    from qoresence.sync.seqgate import lease_layer

    a = acquire_capture_lease("USB3.0 Video", lock_dir=tmp_path)
    try:
        layer = lease_layer(device="USB3.0 Video", lock_dir=tmp_path)
        assert layer["ok"] is True
        assert layer["layer"] == "lease"
        assert "pid" in layer
    finally:
        release_capture_lease(a)


def test_apply_to_situation_strips_unlicensed_scores():
    from qoresence.sync.seqgate import NULL_DIGIT, apply_to_situation, license_digits

    sit = {
        "home_score": 21,
        "away_score": 7,
        "score_home": 21,
        "score_away": 7,
        "confirm_ticket_id": "",
        "score_vlm_locked": False,
    }
    gate = license_digits(
        confirm_ticket_id="",
        score_vlm_locked=False,
        path="confirm",
        home_score=21,
        away_score=7,
        live_clock_ns=9,
        frame_seq=3,
    )
    out = apply_to_situation(sit, gate)
    assert out["home_score"] is None
    assert out["away_score"] is None
    assert out["score_home"] is None
    assert out["score_away"] is None
    assert gate["speech"] == NULL_DIGIT
    # Original bag must not be mutated (no last-good alias).
    assert sit["home_score"] == 21


def test_agent_glass_snapshot_strips_unlicensed_digits():
    from qoresence.agents.agent_glass import AgentGlass
    from qoresence.sync.seqgate import NULL_DIGIT

    g = AgentGlass(
        situation_provider=lambda: {
            "home_score": 21,
            "away_score": 7,
            "score_vlm_locked": False,
            "path": "confirm",
        }
    )
    snap = g.snapshot()
    assert snap["situation"]["home_score"] is None
    assert snap["situation"]["away_score"] is None
    assert snap["seqgate"]["licensed"] is False
    assert snap["seqgate"]["speech"] == NULL_DIGIT
    assert snap["seqgate"]["bind"]["plane"] == "qoresence-observation"
    assert "21" not in str(snap["seqgate"]["speech"])


def test_agent_glass_snapshot_keeps_licensed_digits():
    from qoresence.agents.agent_glass import AgentGlass

    g = AgentGlass(
        situation_provider=lambda: {
            "home_score": 14,
            "away_score": 10,
            "confirm_ticket_id": "c-1",
            "score_vlm_locked": True,
            "path": "confirm",
            "ticket_crop_hash": "crop-a",
            "crop_hash": "crop-a",
            "same_seq": True,
            "confirm_clock_ns": 1_000,
            "clock_ns": 2_000,
            "frame_seq": 42,
        }
    )
    snap = g.snapshot()
    assert snap["situation"]["home_score"] == 14
    assert snap["situation"]["away_score"] == 10
    assert snap["seqgate"]["licensed"] is True
    assert snap["seqgate"]["speech"] == "14-10"


def test_overlay_fallback_paints_null_digit_when_unlicensed():
    from pathlib import Path

    html = (Path(__file__).resolve().parents[1] / "qoresence" / "deck" / "overlay.html").read_text(
        encoding="utf-8"
    )
    assert "□–□" in html
    assert "SEQGATE" in html or "seqgate" in html
    assert "function digitsLicensed" in html
    compact = html.replace(" ", "")
    assert "licensed?" in compact
    # Unlicensed branch must paint the null digit, not keep last-good sc.
    assert "□–□" in html


def test_mcp_observation_requires_seqgate_not_flag_lock_alone():
    from qoresence.mcp.observation import build_observation
    from qoresence.sync.seqgate import NULL_DIGIT

    unlocked = build_observation(
        situation={
            "game_profile": "madden_27",
            "title_claim": True,
            "home_score": 21,
            "away_score": 7,
            "score_vlm_locked": True,
            "scoreboard_locked": True,
        },
        video={"has_frame": True},
    )
    assert unlocked["score"]["claim"] is False
    assert unlocked["score"]["home"] is None
    assert "21-7" not in " ".join(unlocked["may_say"])
    assert unlocked["seqgate"]["speech"] == NULL_DIGIT
    assert unlocked["seqgate"]["licensed"] is False

    locked = build_observation(
        situation={
            "game_profile": "madden_27",
            "title_claim": True,
            "title_hysteresis": "locked",
            "home_score": 14,
            "away_score": 10,
            "score_vlm_locked": True,
            "confirm_ticket_id": "c-1",
            "path": "confirm",
            "ticket_crop_hash": "crop-a",
            "crop_hash": "crop-a",
            "same_seq": True,
            "confirm_clock_ns": 1_000,
            "clock_ns": 2_000,
            "frame_seq": 12,
        },
        video={"has_frame": True, "seq": 12},
        coupling={"phrase": "SNAP", "coupling": 0.6, "frame_seq": 12},
        glass_link={"url": "http://192.168.1.9:8765/mobile.html", "lan": True},
        clock_ns=2_000,
        seq=12,
    )
    assert locked["score"] == {"claim": True, "home": 14, "away": 10}
    assert any("14-10" in s for s in locked["may_say"])
    assert locked["seqgate"]["licensed"] is True
    assert locked["seqgate"]["speech"] == "14-10"
