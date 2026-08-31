"""Look-license graphs: next look only. Flag off equals main."""

from __future__ import annotations

import pytest

from qoresence.agents.drive_graph import DriveGraph
from qoresence.core.unified_config import RetinaUnifiedConfig
from qoresence.deck.live_paint import SAME_SEQ_SLACK, decide_live_paint
from qoresence.graphs import reset_all
from qoresence.graphs.crop_evidence import (
    licensed_crops,
    record_lock,
    record_ticker_null,
)
from qoresence.graphs.flags import ENV_NAME, closeout_applied, enabled, graph_enabled
from qoresence.graphs.look_license import (
    append_license,
    load_licenses,
    make_license,
    maybe_constraint_from_license,
)
from qoresence.graphs.negative_evidence import overlay_forbidden, record_absence, skip_look
from qoresence.graphs.refuse_chain import apply_refuse, mint_blocked
from qoresence.graphs.same_seq_join import classify_join, confirm_look_allowed
from qoresence.graphs.scale_stack import confirm_allowed, confirm_from_tick_alone, license_scale
from qoresence.graphs.ticket_provenance import (
    identity_blocked,
    last_edge,
    next_confirm_look,
    record_refuse,
)
from qoresence.sync.coupling_ticket import mint_coupling_ticket
from qoresence.vision.confirm_ticket import (
    ConfirmTicketBook,
    ConfirmTicketSourceError,
    get_ticket_book,
    mint_confirm_ticket,
)
from qoresence.vision.scorebug_crops import (
    CFB_PRIMARY_SCOREBUG,
    CFB_SCOREBUG_CROPS,
    MADDEN_SCOREBUG_CROPS,
    scorebug_crops_for_profile,
)
from qoresence.vision.title_presence_wrap import dest_denied


def _ticket(**kw):
    return mint_confirm_ticket(
        session_id=kw.get("session_id", "sess_look"),
        clock_ns=kw.get("clock_ns", 1_000),
        home_score=kw.get("home_score", 21),
        away_score=kw.get("away_score", 14),
        source=kw.get("source", "deepseek"),
        frame_seq=kw.get("frame_seq", 12),
        crop_hash=kw.get("crop_hash", "abc"),
        book=kw.get("book"),
        home_team=kw.get("home_team", "DAL"),
        away_team=kw.get("away_team", "NO"),
    )


@pytest.fixture(autouse=True)
def _graphs_off(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_NAME, raising=False)
    for key in (
        "QORESENCE_LOOK_TICKET_DAG",
        "QORESENCE_LOOK_CROP",
        "QORESENCE_LOOK_SAME_SEQ",
        "QORESENCE_LOOK_REFUSE",
        "QORESENCE_LOOK_SCALE",
        "QORESENCE_LOOK_NEGATIVE",
        "QORESENCE_LEARNING_EDGE",
        "QORESENCE_LOOK_LICENSES_PATH",
        "QORESENCE_LEARNING_CONSTRAINTS_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(tmp_path / "look.jsonl"))
    reset_all()
    get_ticket_book().clear()
    try:
        from qoresence.sync.hid_seq_line import get_hid_seq_line

        get_hid_seq_line().clear()
    except Exception:
        pass
    yield
    reset_all()
    get_ticket_book().clear()
    try:
        from qoresence.sync.hid_seq_line import get_hid_seq_line

        get_hid_seq_line().clear()
    except Exception:
        pass


def _on(monkeypatch):
    monkeypatch.setenv(ENV_NAME, "1")
    reset_all()
    monkeypatch.setenv(ENV_NAME, "1")


# ── Substrate ──────────────────────────────────────────────────────────────


def test_flag_off_by_default_and_play_does_not_enable():
    assert enabled() is False
    assert graph_enabled("ticket_provenance") is False
    assert RetinaUnifiedConfig().look_graphs is False
    src = __import__("pathlib").Path("qoresence/cli.py").read_text(encoding="utf-8")
    assert "look_graphs=True" not in src
    play_idx = src.find('if getattr(args, "play", False):')
    assert play_idx != -1
    play_block = src[play_idx : play_idx + 8000]
    assert "look_graphs" not in play_block


def test_make_license_refuses_score_digits_and_frozen_fields():
    assert (
        make_license(
            graph="ticket_provenance",
            kind="mint",
            permits={"home_score": 21},
        )
        is None
    )
    assert (
        make_license(
            graph="ticket_provenance",
            kind="mint",
            permits={"next_action": "21-14"},
        )
        is None
    )
    assert (
        make_license(
            graph="crop_evidence",
            kind="crop_prefer",
            permits={"next_action": "crop", "crop_role": "qortroller-truth"},
        )
        is None
    )
    ok = make_license(graph="ticket_provenance", kind="reuse", permits={"next_action": "keep"})
    assert ok is not None
    assert ok.plane == "qoresence-observation"


def test_flag_off_mint_and_crops_identical_to_baseline():
    book = ConfirmTicketBook()
    a = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=7,
        away_score=0,
        book=book,
        home_team="DAL",
        away_team="NO",
    )
    book.put(a, home_team="DAL", away_team="NO")
    b = mint_confirm_ticket(
        session_id="s",
        clock_ns=2,
        home_score=7,
        away_score=0,
        book=book,
        home_team="DAL",
        away_team="NO",
    )
    assert a.ticket_id == b.ticket_id
    assert scorebug_crops_for_profile(None) is CFB_SCOREBUG_CROPS
    assert scorebug_crops_for_profile("madden_27") is MADDEN_SCOREBUG_CROPS
    assert last_edge() is None
    assert closeout_applied() is None
    assert licensed_crops("ncaa_football_27", CFB_SCOREBUG_CROPS) is None


def test_flag_off_does_not_write_jsonl(tmp_path, monkeypatch):
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    mint_confirm_ticket(session_id="s", clock_ns=1, home_score=3, away_score=0)
    record_refuse("refuse_zero_zero")
    record_lock("ncaa_football_27", crop=list(CFB_PRIMARY_SCOREBUG), bands=CFB_SCOREBUG_CROPS)
    classify_join(live_seq=10, widget_seq=10)
    apply_refuse("menu")
    license_scale("tick")
    record_absence("blank")
    assert not path.exists() or path.read_text(encoding="utf-8") == ""


# ── P1 ticket provenance ───────────────────────────────────────────────────


def test_reuse_remint_refuse_edges(monkeypatch, tmp_path):
    _on(monkeypatch)
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(tmp_path / "look.jsonl"))
    book = ConfirmTicketBook()
    t1 = mint_confirm_ticket(
        session_id="s",
        clock_ns=10,
        home_score=7,
        away_score=0,
        book=book,
        home_team="DAL",
        away_team="NO",
        crop_hash="c1",
    )
    book.put(t1, home_team="DAL", away_team="NO")
    assert last_edge() is not None
    assert last_edge().kind == "mint"
    t2 = mint_confirm_ticket(
        session_id="s",
        clock_ns=20,
        home_score=7,
        away_score=0,
        book=book,
        home_team="DAL",
        away_team="NO",
        crop_hash="c1",
    )
    assert t2.ticket_id == t1.ticket_id
    assert last_edge().kind == "reuse"
    look = next_confirm_look()
    assert look is not None
    assert look.permits["next_action"] == "keep"
    t3 = mint_confirm_ticket(
        session_id="s",
        clock_ns=30,
        home_score=14,
        away_score=0,
        book=book,
        home_team="DAL",
        away_team="NO",
        crop_hash="c1",
    )
    assert t3.ticket_id != t1.ticket_id
    assert last_edge().kind == "remint"
    assert last_edge().permits["keep_crop"] is True
    rec = record_refuse("refuse_zero_zero", session_id="s", clock_ns=40)
    assert rec is not None
    assert rec.kind == "refuse"
    assert "refuse_zero_zero" in rec.refuses
    nxt = next_confirm_look()
    assert nxt.permits["reuse_identity"] is False
    assert identity_blocked() is True
    lines = load_licenses(tmp_path / "look.jsonl")
    kinds = [x.kind for x in lines]
    assert "mint" in kinds
    assert "reuse" in kinds
    assert "remint" in kinds
    assert "refuse" in kinds


def test_provenance_records_outside_book_lock(monkeypatch):
    _on(monkeypatch)
    book = ConfirmTicketBook()
    held = []

    def _during_record(*_a, **_k):
        held.append(book._lock.locked())
        return None

    import qoresence.graphs.ticket_provenance as tp

    orig = tp.append_license

    def _wrap(lic, path=None):
        held.append(book._lock.locked())
        return orig(lic, path)

    monkeypatch.setattr(tp, "append_license", _wrap)
    t = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=3,
        away_score=0,
        book=book,
    )
    book.put(t)
    assert held
    assert all(v is False for v in held)


def test_source_error_records_refuse_when_on(monkeypatch):
    _on(monkeypatch)
    with pytest.raises(ConfirmTicketSourceError):
        mint_confirm_ticket(session_id="s", clock_ns=1, home_score=1, away_score=0, source="society")
    assert last_edge() is not None
    assert last_edge().kind == "refuse"


# ── P2 crop evidence ───────────────────────────────────────────────────────


def test_crop_reorder_existing_bands_only(monkeypatch):
    _on(monkeypatch)
    locked = record_lock(
        "ncaa_football_27",
        crop_index=1,
        bands=CFB_SCOREBUG_CROPS,
        ticket_id="deadbeefdeadbeef",
    )
    assert locked is not None
    out = scorebug_crops_for_profile("ncaa_football_27")
    assert out[0] == CFB_SCOREBUG_CROPS[1]
    assert set(out) == set(CFB_SCOREBUG_CROPS)
    assert all(b in CFB_SCOREBUG_CROPS for b in out)


def test_ticker_null_selects_next_fallback(monkeypatch):
    _on(monkeypatch)
    rec = record_ticker_null("madden_27", from_index=0, bands=MADDEN_SCOREBUG_CROPS)
    assert rec is not None
    assert rec.kind == "crop_fallback"
    out = scorebug_crops_for_profile("madden_27")
    assert out[0] == MADDEN_SCOREBUG_CROPS[1]
    assert set(out) == set(MADDEN_SCOREBUG_CROPS)


# ── P3 Same-Seq ────────────────────────────────────────────────────────────


def test_seq_skew_refuses_confirm_slack_holds(monkeypatch):
    _on(monkeypatch)
    ok = classify_join(live_seq=100, widget_seq=100)
    assert ok is not None and ok.kind == "join_ok"
    assert confirm_look_allowed(ok) is True
    slack = classify_join(live_seq=100, widget_seq=100 - SAME_SEQ_SLACK)
    assert slack is not None and slack.kind == "slack_hold"
    assert confirm_look_allowed(slack) is True
    skew = classify_join(live_seq=100, widget_seq=100 - SAME_SEQ_SLACK - 1)
    assert skew is not None and skew.kind == "seq_skew"
    assert confirm_look_allowed(skew) is False
    dim = classify_join(live_seq=100, widget_seq=100, plane_dim=True)
    assert dim.kind == "plane_dim"
    assert confirm_look_allowed(dim) is False
    paint = decide_live_paint(has_frame=True, live_seq=50, widget_seq=50, game_state="gameplay")
    assert paint.same_seq is True
    ticket = mint_coupling_ticket(
        clock_ns=1,
        frame_seq=50,
        phrase="SNAP",
        coupling=0.8,
        hold_energy=0.4,
        pll_lock=True,
        video_fresh=True,
        same_seq=False,
    )
    assert ticket is None


# ── P4 refuse chain ────────────────────────────────────────────────────────


def test_identity_swap_chain_blocks_stale_identity(monkeypatch):
    _on(monkeypatch)
    lic = apply_refuse("identity_swap", session_id="s", clock_ns=5)
    assert lic is not None
    assert "mint_blocked" in lic.refuses
    assert lic.permits["reuse_identity"] is False
    assert mint_blocked() is True
    assert identity_blocked() is True
    nxt = next_confirm_look()
    assert nxt is not None
    assert nxt.permits["reuse_identity"] is False
    quota = apply_refuse("vlm_quota")
    assert quota is not None
    assert quota.permits.get("constraint_kind") == "schedule_skip"
    menu = apply_refuse("menu")
    assert menu.kind == "pause_crops_only"


# ── P5 scale stack ─────────────────────────────────────────────────────────


def test_confirm_not_licensed_from_tick_alone(monkeypatch):
    _on(monkeypatch)
    assert confirm_from_tick_alone() is False
    tick = license_scale("tick", look="confirm")
    assert tick is not None
    assert tick.kind == "scale_refuse"
    assert tick.permits["next_action"] == "refuse"
    peek = license_scale("tick", look="peek")
    assert peek.kind == "tick_peek"
    phrase = license_scale("phrase", look="confirm", lower_licensed=True)
    assert phrase.kind == "scale_refuse"
    drive = license_scale("drive", look="confirm", lower_licensed=True)
    assert drive.kind == "drive_confirm"
    assert confirm_allowed(scale="tick") is False
    assert confirm_allowed(scale="drive", lower_licensed=True) is True


# ── P6 negative evidence ───────────────────────────────────────────────────


def test_blank_licenses_skip_not_crop_overlay(monkeypatch):
    _on(monkeypatch)
    lic = record_absence("blank")
    assert lic is not None
    assert lic.kind == "skip_look"
    assert lic.permits["next_action"] == "skip"
    assert "crop" not in lic.permits
    assert skip_look() is True
    assert overlay_forbidden() is True
    overlay = record_absence("overlay_rejected")
    assert overlay.permits.get("crop_role") == "pause"
    denied = record_absence("dest_denied")
    assert denied.permits["next_action"] == "skip"
    assert dest_denied("qortroller-truth") is True


def test_learning_edge_bridge_requires_both_flags(monkeypatch):
    _on(monkeypatch)
    lic = make_license(
        graph="crop_evidence",
        kind="crop_prefer",
        permits={
            "next_action": "crop",
            "crop_role": "primary",
            "crop": list(CFB_PRIMARY_SCOREBUG),
            "constraint_kind": "crop_band",
            "profile": "ncaa_football_27",
        },
        source_ticket_id="deadbeefdeadbeef",
    )
    assert maybe_constraint_from_license(lic) is None
    monkeypatch.setenv("QORESENCE_LEARNING_EDGE", "1")
    ticket = _ticket()
    cons = maybe_constraint_from_license(lic, ticket=ticket)
    assert cons is not None
    assert cons.kind == "crop_band"


def test_drivegraph_ranking_unchanged_with_graphs_on(monkeypatch):
    _on(monkeypatch)
    t0 = 0
    events = [
        {
            "clock_ns": t0,
            "kind": "fast_chat",
            "path": "fast",
            "message": "Live-board 0-0",
            "coupling": 0.9,
            "factual": False,
        },
        {
            "clock_ns": t0 + 10_000,
            "kind": "fast_chat",
            "path": "fast",
            "message": "board dump",
            "coupling": 0.8,
            "factual": False,
        },
        {
            "clock_ns": t0 + int(20e9),
            "kind": "confirm_score",
            "path": "confirm",
            "message": "touchdown 7-0",
            "factual": True,
        },
        {
            "clock_ns": t0 + int(21e9),
            "kind": "prediction_resolve",
            "path": "confirm",
            "message": "TD resolved",
            "factual": True,
        },
    ]
    g = DriveGraph.from_events("td", events)
    g.started_ns = t0
    ranked = g.ranked_chapter_nodes(k=3)
    labels = [n.label.lower() for n in ranked]
    assert any(
        "touchdown" in x or n.kind == "confirm_score" for n, x in zip(ranked, labels, strict=True)
    )
    cl = g.climax_score()
    assert cl["best_kind"] in {"confirm_score", "prediction_resolve"}


def test_jsonl_round_trip(monkeypatch, tmp_path):
    _on(monkeypatch)
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    lic = make_license(
        graph="ticket_provenance",
        kind="reuse",
        session_id="s",
        clock_ns=9,
        permits={"next_action": "keep", "reuse_identity": True},
        source_ticket_id="aaaaaaaaaaaaaaaa",
    )
    append_license(lic, path)
    loaded = load_licenses(path)
    assert len(loaded) == 1
    assert loaded[0].kind == "reuse"
    assert loaded[0].source_ticket_id == "aaaaaaaaaaaaaaaa"


def test_per_graph_env_can_dark_ship(monkeypatch):
    _on(monkeypatch)
    monkeypatch.setenv("QORESENCE_LOOK_CROP", "0")
    assert graph_enabled("ticket_provenance") is True
    assert graph_enabled("crop_evidence") is False
    assert record_lock("ncaa_football_27", crop_index=0, bands=CFB_SCOREBUG_CROPS) is None
    assert scorebug_crops_for_profile(None) is CFB_SCOREBUG_CROPS


# ── P7 look gate (enforce licenses) ────────────────────────────────────────


def test_gate_off_permits_everything():
    from qoresence.graphs.look_gate import (
        permit_confirm_look,
        permit_confirm_mint,
        permit_ocr_look,
    )

    assert permit_confirm_look(reason="tick") is True
    assert permit_ocr_look() is True
    assert permit_confirm_mint(reuse=True) is True
    assert permit_confirm_mint(reuse=False) is True


def test_gate_tick_alone_refuses_confirm_vlm(monkeypatch):
    from qoresence.graphs.look_gate import permit_confirm_look

    _on(monkeypatch)
    assert permit_confirm_look(reason="tick") is False
    assert permit_confirm_look(reason="tick", has_frame=False) is False
    assert permit_confirm_look(reason="tick", blank=True) is False
    assert permit_confirm_look(reason="score_changed") is True
    assert permit_confirm_look(reason="tick", force=True) is True


def test_gate_tick_with_open_drive_allows_confirm(monkeypatch):
    from qoresence.graphs.look_gate import permit_confirm_look

    _on(monkeypatch)

    class _Drive:
        drive_id = "d1"

    class _Tl:
        def active_drive(self):
            return _Drive()

    monkeypatch.setattr(
        "qoresence.graphs.look_gate._active_drive",
        lambda: True,
    )
    assert permit_confirm_look(reason="tick") is True


def test_gate_seq_skew_refuses_vlm_and_ocr(monkeypatch):
    from qoresence.graphs.look_gate import permit_confirm_look, permit_ocr_look

    _on(monkeypatch)
    classify_join(live_seq=100, widget_seq=1)
    monkeypatch.setattr("qoresence.graphs.look_gate._active_drive", lambda: True)
    assert permit_confirm_look(reason="score_changed") is False
    assert permit_ocr_look() is False


def test_gate_blocks_stale_reuse_allows_remint(monkeypatch):
    from qoresence.graphs.look_gate import permit_confirm_mint

    _on(monkeypatch)
    apply_refuse("identity_swap")
    assert permit_confirm_mint(reuse=True) is False
    assert permit_confirm_mint(reuse=False) is True


def test_may_confirm_does_not_write_jsonl(monkeypatch, tmp_path):
    from qoresence.graphs.scale_stack import may_confirm

    _on(monkeypatch)
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    assert may_confirm(scale="tick") is False
    assert may_confirm(scale="drive") is True
    assert not path.exists() or path.read_text(encoding="utf-8") == ""


def test_vlm_schedule_skips_tick_when_gate_refuses(monkeypatch):
    import numpy as np

    from qoresence.vision.scoreboard_vlm import ScoreboardVlmReferee

    _on(monkeypatch)
    ref = ScoreboardVlmReferee.__new__(ScoreboardVlmReferee)
    ref.enabled = True
    called = []
    monkeypatch.setattr(ref, "_crop", lambda *a, **k: called.append("crop") or np.zeros((8, 8, 3)))
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    ref.schedule(frame, game_state="gameplay", game_profile="cfb_27", reason="tick")
    assert called == []


# ── P8 apply licenses to next look / splitter ──────────────────────────────


def test_civif_tick_is_peek_not_confirm_and_writes_no_jsonl(monkeypatch, tmp_path):
    from qoresence.core.civif_tick import build_coupled_tick
    from qoresence.graphs.look_gate import permit_confirm_look
    from qoresence.graphs.scale_stack import licensed_scale

    _on(monkeypatch)
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    rec = build_coupled_tick(coupling={"video_clock_ns": 1, "frame_seq": 3})
    assert rec.frame_seq == 3
    assert licensed_scale() == "tick"
    assert permit_confirm_look(reason="tick") is False
    if path.exists():
        assert "tick_peek" not in path.read_text(encoding="utf-8")


def test_drive_open_escalates_confirm_look(monkeypatch):
    from qoresence.agents.session_timeline import reset_session_timeline
    from qoresence.graphs.look_gate import permit_confirm_look
    from qoresence.graphs.scale_stack import licensed_scale

    _on(monkeypatch)
    tl = reset_session_timeline()
    try:
        tl.append(kind="arm", path="fast", open_drive=True, clock_ns=10, frame_seq=4)
        assert licensed_scale() == "drive"
        assert permit_confirm_look(reason="tick") is True
        tl.append(kind="resolve", path="confirm", close_drive=True, clock_ns=20)
        assert licensed_scale() == "tick"
        assert permit_confirm_look(reason="tick") is False
    finally:
        reset_session_timeline()


def test_quota_skip_refuses_vlm_and_drops_confirm_chapters(monkeypatch):
    from qoresence.agents.learning_edge import split_chapter_units
    from qoresence.graphs.look_gate import permit_confirm_look

    _on(monkeypatch)
    apply_refuse("vlm_quota")
    monkeypatch.setattr("qoresence.graphs.look_gate._active_drive", lambda: True)
    assert permit_confirm_look(reason="tick") is False
    assert permit_confirm_look(reason="score_changed") is False
    t0 = 0
    events = [
        {
            "clock_ns": t0,
            "kind": "fast_chat",
            "path": "fast",
            "message": "Live-board 0-0",
            "coupling": 0.9,
            "factual": False,
        },
        {
            "clock_ns": t0 + int(20e9),
            "kind": "confirm_score",
            "path": "confirm",
            "message": "touchdown 7-0",
            "factual": True,
        },
    ]
    g = DriveGraph.from_events("td", events)
    kept, lite = split_chapter_units(g, k=8)
    assert all(n.kind not in {"confirm", "confirm_score"} for n in kept)
    assert lite.receipts == ()


def test_dual_flag_refuse_writes_existing_constraint_kind(monkeypatch, tmp_path):
    from qoresence.agents.learning_constraint import load_constraints

    _on(monkeypatch)
    monkeypatch.setenv("QORESENCE_LEARNING_EDGE", "1")
    dest = tmp_path / "c.jsonl"
    monkeypatch.setenv("QORESENCE_LEARNING_CONSTRAINTS_PATH", str(dest))
    t = mint_confirm_ticket(
        session_id="s",
        clock_ns=1,
        home_score=7,
        away_score=0,
        source="deepseek",
    )
    get_ticket_book().put(t)
    apply_refuse("vlm_quota")
    cons = load_constraints(dest)
    assert cons
    assert cons[-1].kind == "schedule_skip"
    assert cons[-1].source_ticket_id == t.ticket_id


def test_look_graphs_off_splitter_still_keeps_confirm():
    from qoresence.agents.learning_edge import split_chapter_units

    t0 = 0
    events = [
        {
            "clock_ns": t0 + int(20e9),
            "kind": "confirm_score",
            "path": "confirm",
            "message": "touchdown 7-0",
            "factual": True,
        },
    ]
    g = DriveGraph.from_events("td", events)
    nodes = g.ranked_chapter_nodes(k=8)
    kept, _ = split_chapter_units(g, k=8)
    assert [n.node_id for n in kept] == [n.node_id for n in nodes]


# ── P9 operator snapshot + Same-Seq JSONL dedup ────────────────────────────


def test_look_gate_snapshot_omitted_when_flag_off():
    from qoresence.deck.seeing_health import attach_board_health
    from qoresence.graphs.look_gate import snapshot
    from qoresence.pilot import closeout

    assert snapshot() is None
    out = attach_board_health({}, {"confirm_ticket_id": "secret-ticket-id"})
    assert "look_scale" not in out
    assert "look_join" not in out
    assert "look_permit_confirm" not in out
    assert "look_refuse" not in out
    summary = closeout.summarize([])
    assert "look_gate" not in summary
    assert "look_licenses_applied" not in summary


def test_look_gate_snapshot_on_health_has_no_ticket_or_score(monkeypatch):
    import json

    from qoresence.deck.seeing_health import attach_board_health
    from qoresence.graphs.look_gate import snapshot
    from qoresence.pilot import closeout

    _on(monkeypatch)
    classify_join(live_seq=20, widget_seq=20)
    snap = snapshot()
    assert snap is not None
    assert set(snap) == {"scale", "join", "permit_confirm", "refuse"}
    assert snap["join"] == "join_ok"
    assert snap["scale"] == "tick"
    assert snap["permit_confirm"] is False
    assert "scale_tick" in str(snap["refuse"])
    blob = json.dumps(snap)
    assert "ticket" not in blob.lower()
    assert "score" not in blob.lower()
    assert "21" not in blob and "14" not in blob

    out = attach_board_health(
        {},
        {"confirm_ticket_id": "secret-ticket-id", "home_score": 21, "away_score": 14},
    )
    assert out["look_join"] == "join_ok"
    assert out["look_scale"] == "tick"
    assert out["look_permit_confirm"] is False
    assert "scale_tick" in out["look_refuse"]
    look_blob = json.dumps({k: out[k] for k in out if str(k).startswith("look_")})
    assert "secret-ticket-id" not in look_blob
    assert "21" not in look_blob
    assert "ticket" not in look_blob.lower()

    summary = closeout.summarize([])
    assert "look_gate" in summary
    assert summary["look_gate"]["join"] == "join_ok"
    assert "look_licenses_applied" in summary
    assert "secret-ticket-id" not in json.dumps(summary["look_gate"])


def test_look_gate_snapshot_does_not_write_jsonl(monkeypatch, tmp_path):
    from qoresence.graphs.look_gate import snapshot

    _on(monkeypatch)
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    snap = snapshot()
    assert snap is not None
    assert not path.exists() or path.read_text(encoding="utf-8") == ""


def test_classify_join_dedups_unchanged_sig(monkeypatch, tmp_path):
    _on(monkeypatch)
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    a = classify_join(live_seq=40, widget_seq=40, hid_seq=40)
    b = classify_join(live_seq=40, widget_seq=40, hid_seq=40)
    assert a is not None and b is not None
    assert a.id == b.id
    assert a is b
    rows = load_licenses(path)
    assert len(rows) == 1
    c = classify_join(live_seq=41, widget_seq=41, hid_seq=41)
    assert c is not None and c.id != a.id
    assert len(load_licenses(path)) == 2
    skew = classify_join(live_seq=41, widget_seq=1, hid_seq=41)
    assert skew is not None and skew.kind == "seq_skew"
    assert len(load_licenses(path)) == 3


# ── P10 live apply: HID join, session wrap, /health patch at deck boot ──


def test_live_paint_reads_ghost_stick_hid_seq(monkeypatch):
    from qoresence.graphs.same_seq_join import last_license, record_live_paint
    from qoresence.sync.hid_seq_line import HidSeqSample, get_hid_seq_line, put_sample

    _on(monkeypatch)
    put_sample(
        HidSeqSample(
            hub_seq=10,
            hub_clock_ns=1,
            hid_clock_ns=1,
            lx=0.1,
            ly=0.0,
            r2=0.0,
            l2=0.0,
            buttons=(),
            hid_domain="test",
        )
    )
    aligned = decide_live_paint(has_frame=True, live_seq=10, widget_seq=10, game_state="gameplay")
    assert aligned.same_seq is True
    lic = last_license()
    assert lic is not None and lic.kind == "join_ok"
    get_hid_seq_line().clear()
    put_sample(
        HidSeqSample(
            hub_seq=1,
            hub_clock_ns=1,
            hid_clock_ns=1,
            lx=0.1,
            ly=0.0,
            r2=0.0,
            l2=0.0,
            buttons=(),
            hid_domain="test",
        )
    )
    paint = type(aligned)(
        aligned.paint,
        100,
        100,
        True,
        False,
        "ok",
        True,
    )
    hid_skew = record_live_paint(paint)
    assert hid_skew is not None and hid_skew.kind == "seq_skew"
    from qoresence.graphs.look_gate import permit_ocr_look

    assert permit_ocr_look() is False


def test_write_closeout_notes_session_wrap(monkeypatch, tmp_path):
    from qoresence.graphs.scale_stack import licensed_scale
    from qoresence.pilot import closeout

    _on(monkeypatch)
    path = tmp_path / "look.jsonl"
    monkeypatch.setenv("QORESENCE_LOOK_LICENSES_PATH", str(path))
    session = tmp_path / "session_p10.jsonl"
    session.write_text(
        '{"ts":"t0","clock_ns":0,"video_age_s":0.1,"frames":1,"has_frame":true,'
        '"score_home":7,"score_away":0,"score_vlm_locked":true,"flags":[]}\n',
        encoding="utf-8",
    )
    _j, _md, summary = closeout.write_closeout(session)
    assert licensed_scale() == "session"
    assert summary["look_gate"]["scale"] == "session"
    kinds = [lic.kind for lic in load_licenses(path)]
    assert "session_wrap" in kinds


def test_deck_boot_installs_health_look_keys(monkeypatch):
    from qoresence.deck.seeing_health import install_health_patch
    from qoresence.deck.server import DeckState, create_app

    _on(monkeypatch)
    create_app()
    install_health_patch()
    st = DeckState()
    snap = st._snapshot_fresh()
    assert "look_scale" in snap
    assert "look_join" in snap
    assert "look_permit_confirm" in snap
    assert "look_refuse" in snap
    assert "ticket" not in str(snap.get("look_scale"))
    assert snap.get("confirm_ticket_id") is None
