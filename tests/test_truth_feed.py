"""Truth feed: fail-closed facts, hash chain, signatures, deck endpoints, no blocking."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from qoresence.truth import chain as chain_mod
from qoresence.truth import feed as feed_mod
from qoresence.truth.chain import verify_file
from qoresence.truth.feed import TruthFeed, TruthFeedConfig, corroborate_input, parse_locked_score
from qoresence.truth.signing import crypto_available, load_or_create_signer

ROOT = Path(__file__).resolve().parents[1]
needs_crypto = pytest.mark.skipif(not crypto_available(), reason="cryptography not installed")


def _payload(home, away, *, locked=True, tid="tkt-1", ticket=True, crop="c0ffee", **ticket_over):
    t = {
        "ticket_id": tid,
        "session_id": "s",
        "clock_ns": time.monotonic_ns(),
        "home_score": home,
        "away_score": away,
        "model": "local_scorebug_v1",
        "source": "local_scorebug",
        "frame_seq": 41,
        "crop_hash": crop,
        "observed_clock_ns": time.monotonic_ns(),
        "observed_frame_seq": 42,
        "observed_crop_hash": crop,
    }
    t.update(ticket_over)
    return {
        "game_profile": "madden_27",
        "score_vlm_locked": locked,
        "confirm_ticket_id": tid if locked else None,
        "football": {"home_score": home, "away_score": away, "home_team": "KC", "away_team": "BUF"},
        "details": {"confirm_ticket": t} if ticket else {},
        "frame_hash": "f" * 16,
        "model": "local_scorebug_v1",
    }


def _event(payload, etype="visual_context"):
    return SimpleNamespace(
        type=SimpleNamespace(value=etype),
        payload=payload,
        session_id="bus-s",
        clock_ns=time.monotonic_ns(),
    )


LIVE = {"has_frame": True, "age_s": 0.1, "seq": 42}


def _feed(tmp_path, *, signer=None, events=None, stamp=LIVE, **cfg):
    config = TruthFeedConfig(enabled=True, out_dir=str(tmp_path / "truth"), **cfg)
    f = TruthFeed(
        config,
        session_id="sess-1",
        signer=signer,
        sign_reason="test" if signer is None else "ok",
        frame_stamp=lambda: stamp,
        input_window=lambda a, b: list(events or []),
    )
    f.start()  # no bus; tests drive on_event + step
    return f


def _facts(f, kind=None):
    rows = f.recent(limit=500)
    return [r for r in rows if kind is None or r["kind"] == kind]


def _lines(f):
    return f.path.read_text(encoding="utf-8").splitlines()


# ── fail-closed emission ──────────────────────────────────────────────────────


def test_lock_change_hold_and_reset(tmp_path):
    f = _feed(tmp_path)
    f.on_event(_event(_payload(7, 3)))
    f.on_event(_event(_payload(7, 3)))  # held lock → deduped
    f.on_event(_event(_payload(14, 3, tid="tkt-2")))
    f.on_event(_event(_payload(0, 3, tid="tkt-3")))  # decrease → baseline only
    assert f.step() == 3
    kinds = [r["kind"] for r in _facts(f)]
    assert kinds == ["session_start", "score_lock", "score_change", "score_lock"]
    lock, change, reset = _facts(f)[1:]
    assert lock["scores"]["home"] == 7 and lock["prev_scores"] is None
    assert change["prev_scores"] == {"home": 7, "away": 3}
    assert change["scores"] == {**change["scores"], "home": 14, "away": 3}
    assert change["source"]["reader"] == "local_scorebug"
    assert change["source"]["plane"] == "local"
    assert change["frame"]["lock_crop_hash"] == "c0ffee"
    assert change["frame"]["frame_seq"] == 42
    assert reset["meta"] == {"baseline_reset": True}
    assert change["verification"]["label"] == "unverified"  # no controller input
    assert change["verification"]["level"] == "screen_only"
    assert change["controller"] is None
    f.stop()


@pytest.mark.parametrize(
    "payload,reason",
    [
        (_payload(7, 3, locked=False), None),  # dropped on the bus thread
        (_payload(None, None), "blank_board"),
        (_payload(7, 3, ticket=False), "no_ticket"),
        (_payload(7, 3, tid=""), "no_ticket_id"),
        (_payload(7, 3, home_score=9), "ticket_digits_mismatch"),
        (_payload(7, 3, ticket_id="other"), "ticket_id_mismatch"),
        (_payload(0, 0), "ticket_not_licensed"),  # kickoff 0-0 never licensed
        (_payload(7, 3, crop=""), "ticket_not_licensed"),  # no crop hash
        (_payload(7, 3, observed_clock_ns=1), "ticket_not_licensed"),  # stale ticket
    ],
)
def test_no_fact_for_unlocked_blank_or_unlicensed(tmp_path, payload, reason):
    f = _feed(tmp_path)
    f.on_event(_event(payload))
    assert f.step() == 0
    assert _facts(f, "score_lock") == [] and _facts(f, "score_change") == []
    if reason:
        assert f.refused.get(reason) == 1, f.refused
    f.stop()


def test_no_fact_when_capture_not_live(tmp_path):
    for stamp in ({"has_frame": False}, {"has_frame": True, "age_s": 30.0}):
        f = _feed(tmp_path / str(len(str(stamp))), stamp=stamp)
        f.on_event(_event(_payload(7, 3)))
        assert f.step() == 0
        assert f.refused == {"capture_not_live": 1}
        f.stop()


def test_ignores_other_event_types(tmp_path):
    f = _feed(tmp_path)
    f.on_event(_event(_payload(7, 3), etype="presence_report"))
    f.on_event(SimpleNamespace())  # malformed: never raises
    assert f.step() == 0 and f.events_seen == 0
    f.stop()


def test_parse_reader_plane_cloud():
    lock, why = parse_locked_score(
        _payload(7, 3, source="gemini", model="gemini-3.5-flash-lite"), licensed=lambda t: True
    )
    assert why == "ok" and lock["source"]["plane"] == "cloud"


# ── controller corroboration ──────────────────────────────────────────────────


def _ev(kind, domain, dt_s=2.0):
    return SimpleNamespace(
        clock_ns=time.monotonic_ns() - int(dt_s * 1e9), kind=kind, name="cross", hid_domain=domain
    )


def test_play_input_corroborates(tmp_path):
    evs = [_ev("press", "play", 5), _ev("release", "play", 4.9), _ev("press", "play", 3)]
    f = _feed(tmp_path, events=evs)
    f.on_event(_event(_payload(7, 3)))
    f.step()
    fact = _facts(f, "score_lock")[0]
    assert fact["verification"] == {"level": "screen+input", "label": "verified", "reasons": []}
    assert fact["controller"]["play_presses"] == 2
    assert fact["controller"]["depth"] == "presence_only"
    f.stop()


def test_observe_domain_never_corroborates():
    evs = [_ev("press", "observe"), _ev("press", "observe"), _ev("press", "picture")]
    summary, level, reasons = corroborate_input(
        evs, t_lock_ns=time.monotonic_ns(), window_s=15, min_presses=2
    )
    assert level == "screen_only" and reasons == ["observe_domain_only"]
    assert summary["play_events"] == 0
    s2, l2, r2 = corroborate_input(None, t_lock_ns=0, window_s=15, min_presses=2)
    assert s2 is None and l2 == "screen_only" and r2 == ["input_ring_unavailable"]


# ── chain + signatures ────────────────────────────────────────────────────────


def _make_session(tmp_path, signer=None):
    f = _feed(tmp_path, signer=signer)
    for i, (h, a) in enumerate([(7, 0), (7, 3), (14, 3)]):
        f.on_event(_event(_payload(h, a, tid=f"t{i}")))
    f.step()
    f.stop()
    return f


def test_unsigned_chain_verifies_and_says_so(tmp_path):
    f = _make_session(tmp_path)
    res = verify_file(f.path)
    assert res["ok"] and res["count"] == 5 and res["complete"]
    assert res["signed"] is False
    for line in _lines(f):
        rec = json.loads(line)
        assert rec["signed"] is False and rec["signature"] is None and rec["key_id"] is None


def test_tamper_detection(tmp_path):
    f = _make_session(tmp_path)
    lines = _lines(f)
    rec = json.loads(lines[2])
    rec["scores"]["home"] = 99
    bad = lines[:2] + [json.dumps(rec)] + lines[3:]
    res = chain_mod.verify_records(bad)
    assert not res["ok"] and any(e["error"] == "hash_mismatch" for e in res["errors"])
    # Recomputing the hash still breaks the next link.
    from qoresence.truth.model import fact_hash

    rec["hash"] = fact_hash(rec)
    res = chain_mod.verify_records(lines[:2] + [json.dumps(rec)] + lines[3:])
    assert any(e["error"] == "prev_hash_mismatch" for e in res["errors"])
    # Deleting a line is a seq gap + broken link.
    res = chain_mod.verify_records(lines[:2] + lines[3:])
    errs = {e["error"] for e in res["errors"]}
    assert "prev_hash_mismatch" in errs and any(x.startswith("seq_gap") for x in errs)
    # A forged "verified" label is rejected even with a recomputed hash chain.
    first = json.loads(lines[1])
    first["verification"]["label"] = "verified"
    first["hash"] = fact_hash(first)
    res = chain_mod.verify_records([lines[0], json.dumps(first)])
    assert any(e["error"] == "verified_label_without_input" for e in res["errors"])


@needs_crypto
def test_signed_chain_and_signature_checks(tmp_path):
    signer, why = load_or_create_signer(tmp_path / "keys" / "truth_key")
    assert why == "ok" and signer is not None
    f = _make_session(tmp_path, signer=signer)
    res = verify_file(f.path, pubkey_hex=signer.pubkey_hex)
    assert res["ok"] and res["signed"] and res["signatures_checked"] == 5
    assert res["pubkey"] == signer.pubkey_hex
    # TOFU: key from session_start
    assert verify_file(f.path)["pubkey_source"] == "session_start"
    # Wrong pinned key fails.
    other, _ = load_or_create_signer(tmp_path / "other" / "truth_key")
    res = verify_file(f.path, pubkey_hex=other.pubkey_hex)
    assert not res["ok"]
    # Stripping a signature (and flipping signed) breaks the chain.
    lines = _lines(f)
    rec = json.loads(lines[2])
    rec["signature"], rec["signed"], rec["key_id"] = None, False, None
    res = chain_mod.verify_records(lines[:2] + [json.dumps(rec)] + lines[3:])
    errs = {e["error"] for e in res["errors"]}
    assert "hash_mismatch" in errs and "mixed_signed_unsigned" in errs
    # A forged signature over a re-hashed body fails.
    from qoresence.truth.model import fact_hash

    rec = json.loads(lines[2])
    rec["scores"]["home"] = 21
    rec["hash"] = fact_hash(rec)
    res = chain_mod.verify_records(lines[:2] + [json.dumps(rec)], pubkey_hex=signer.pubkey_hex)
    assert any(e["error"] == "bad_signature" for e in res["errors"])


@needs_crypto
@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_key_file_created_0600_reused_and_open_perms_refused(tmp_path):
    p = tmp_path / "k" / "truth_key"
    s1, _ = load_or_create_signer(p)
    assert (p.stat().st_mode & 0o777) == 0o600
    assert (p.with_name("truth_key.pub")).read_text().strip() == s1.pubkey_hex
    s2, _ = load_or_create_signer(p)
    assert s2.pubkey_hex == s1.pubkey_hex
    os.chmod(p, 0o644)
    s3, why = load_or_create_signer(p)
    assert s3 is None and why == "key_permissions_too_open"


def test_sign_failure_drops_fact_never_writes_fake_signed(tmp_path):
    class Boom:
        pubkey_hex = "00" * 32
        key_id = "deadbeefdeadbeef"

        def sign(self, data):
            raise OSError("no key")

    f = _feed(tmp_path, signer=Boom())
    assert _lines(f) == []  # even session_start refused
    f.on_event(_event(_payload(7, 3)))
    f.step()
    assert _lines(f) == [] and f.refused.get("sign_failed", 0) >= 1
    f.stop()


@needs_crypto
def test_resume_with_different_signing_mode_starts_new_file(tmp_path):
    f = _make_session(tmp_path)  # unsigned
    signer, _ = load_or_create_signer(tmp_path / "key")
    f2 = _feed(tmp_path, signer=signer)
    f2.stop()
    assert f2.path != f.path and f2.path.name.endswith("_2.jsonl")
    assert verify_file(f.path)["ok"] and verify_file(f2.path)["ok"]


def test_resume_existing_file_keeps_chain(tmp_path):
    f = _make_session(tmp_path)
    f2 = _feed(tmp_path)
    f2.on_event(_event(_payload(21, 3, tid="t9")))
    f2.step()
    f2.stop()
    res = verify_file(f2.path)
    assert res["ok"] and res["count"] == 8  # 5 + start/lock/end


@pytest.mark.parametrize("signed", [False, True])
def test_standalone_script_agrees(tmp_path, signed):
    if signed and not crypto_available():
        pytest.skip("cryptography not installed")
    signer = load_or_create_signer(tmp_path / "key")[0] if signed else None
    f = _make_session(tmp_path, signer=signer)
    script = ROOT / "scripts" / "verify_truth_feed.py"
    r = subprocess.run([sys.executable, str(script), str(f.path), "--json"], capture_output=True)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads(r.stdout)
    assert out == {k: v for k, v in verify_file(f.path).items() if k != "path"}
    lines = _lines(f)
    rec = json.loads(lines[3])
    rec["scores"]["away"] = 0
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(lines[:3] + [json.dumps(rec)] + lines[4:]) + "\n")
    r = subprocess.run([sys.executable, str(script), str(bad)], capture_output=True, text=True)
    assert r.returncode == 1 and "hash_mismatch" in r.stdout


# ── clip_ref ──────────────────────────────────────────────────────────────────


def test_clip_ref_hashes_file_and_links_temporally(tmp_path):
    f = _feed(tmp_path)
    f.on_event(_event(_payload(7, 3)))
    f.step()
    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"mp4bytes")
    f.note_clip({"path": str(clip), "duration_s": 12.0})
    f.note_clip({"path": str(tmp_path / "missing.mp4")})
    f.step()
    ref = _facts(f, "clip_ref")[0]
    import hashlib

    assert ref["clip"]["sha256"] == hashlib.sha256(b"mp4bytes").hexdigest()
    assert ref["clip"]["near_score_seq"] == _facts(f, "score_lock")[0]["seq"]
    assert ref["scores"] is None and ref["verification"]["label"] == "unverified"
    assert f.refused.get("clip_missing") == 1
    f.stop()
    assert verify_file(f.path)["ok"]


def test_note_clip_exported_noop_when_off(tmp_path):
    assert feed_mod.get_truth_feed() is None
    feed_mod.note_clip_exported(tmp_path / "x.mp4", duration_s=1.0)  # no raise


# ── no blocking ───────────────────────────────────────────────────────────────


def test_subscriber_never_blocks_on_slow_worker(tmp_path):
    gate = threading.Event()

    def slow_window(a, b):
        gate.wait(5)
        return []

    config = TruthFeedConfig(enabled=True, out_dir=str(tmp_path / "t"), queue_max=32)
    f = TruthFeed(config, session_id="s", frame_stamp=lambda: LIVE, input_window=slow_window)
    f.start()  # real worker thread
    f.on_event(_event(_payload(7, 3)))
    time.sleep(0.2)  # worker now stuck in slow_window
    t0 = time.perf_counter()
    for i in range(2000):
        f.on_event(_event(_payload(7 + i % 50, 3, tid=f"t{i}")))
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, elapsed
    assert f.dropped > 0  # bounded drop-oldest
    gate.set()
    f.stop()
    assert verify_file(f.path)["ok"]


def test_real_bus_subscription(tmp_path):
    from qoresence.core.event_bus import RetinaEventBus
    from qoresence.core.types import SourceLobe

    bus = RetinaEventBus(session_id="bus-1", jsonl_path=tmp_path / "ev.jsonl", enable_ws=False)
    config = TruthFeedConfig(enabled=True, out_dir=str(tmp_path / "t"))
    f = TruthFeed(
        config, session_id="bus-1", frame_stamp=lambda: LIVE, input_window=lambda a, b: []
    )
    f.start(bus)
    bus.emit_raw(SourceLobe.VISUAL, "visual_context", _payload(10, 7))
    bus.emit_raw(SourceLobe.VISUAL, "visual_context", _payload(10, 7, locked=False))
    deadline = time.time() + 3
    while time.time() < deadline and not _facts(f, "score_lock"):
        time.sleep(0.02)
    f.stop()
    assert [r["kind"] for r in _facts(f)] == ["session_start", "score_lock", "session_end"]


# ── deck endpoints ────────────────────────────────────────────────────────────


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from qoresence.truth.deck_routes import register_fastapi

    app = FastAPI()
    register_fastapi(app)
    client = TestClient(app)
    yield client
    feed_mod.stop_truth_feed()


def test_endpoints_off_return_503(app_client):
    for path in ("/api/truth/feed", "/api/truth/verify", "/api/truth/pubkey", "/api/truth/stream"):
        r = app_client.get(path)
        assert r.status_code == 503 and r.json()["error"] == "truth_feed_off"


def test_endpoints_feed_verify_pubkey_and_sse(app_client, tmp_path, monkeypatch):
    monkeypatch.setattr(feed_mod, "_default_frame_stamp", lambda: LIVE)
    monkeypatch.setattr(feed_mod, "_default_input_window", lambda a, b: [])
    cfg = TruthFeedConfig(
        enabled=True, out_dir=str(tmp_path / "t"), key_path=str(tmp_path / "k" / "truth_key")
    )
    f = feed_mod.make_truth_feed_from_config(cfg, session_id="deck-1")
    f.on_event(_event(_payload(7, 3)))
    f.step()

    r = app_client.get("/api/truth/feed")
    body = r.json()
    assert r.status_code == 200 and [x["kind"] for x in body["facts"]] == [
        "session_start",
        "score_lock",
    ]
    r = app_client.get("/api/truth/feed", params={"since": 0})
    assert [x["seq"] for x in r.json()["facts"]] == [1]

    v = app_client.get("/api/truth/verify").json()
    assert v["ok"] is True and v["count"] == 2
    pk = app_client.get("/api/truth/pubkey").json()
    assert pk["signed"] == crypto_available()
    if crypto_available():
        assert pk["pubkey"] == v["pubkey"] and len(pk["pubkey"]) == 64

    with app_client.stream("GET", "/api/truth/stream", params={"limit_s": 0.3}) as s:
        assert s.headers["content-type"].startswith("text/event-stream")
        text = "".join(s.iter_text())
    assert "event: fact" in text and "id: 1" in text
    data = [json.loads(ln[6:]) for ln in text.splitlines() if ln.startswith("data: ")]
    assert data[-1]["kind"] == "score_lock" and data[-1]["scores"]["home"] == 7

    with app_client.stream(
        "GET", "/api/truth/stream", params={"limit_s": 0.2}, headers={"Last-Event-ID": "1"}
    ) as s:
        assert "event: fact" not in "".join(s.iter_text())


def test_access_lan_denied_by_default(monkeypatch):
    from qoresence.truth.deck_routes import access_denied

    monkeypatch.delenv("QORESENCE_TRUTH_FEED_LAN", raising=False)
    assert access_denied(client_host="127.0.0.1", token_ok=True) is None
    assert access_denied(client_host="192.168.1.20", token_ok=True)[0] == 403
    assert access_denied(client_host="127.0.0.1", token_ok=False)[0] == 401
    monkeypatch.setenv("QORESENCE_TRUTH_FEED_LAN", "1")
    assert access_denied(client_host="192.168.1.20", token_ok=True) is None


def test_off_by_default_no_key_no_files(tmp_path, monkeypatch):
    monkeypatch.delenv("QORESENCE_TRUTH_FEED", raising=False)
    cfg = TruthFeedConfig.from_env()
    assert cfg.enabled is False
    assert feed_mod.make_truth_feed_from_config(cfg) is None


def test_cli_flag_sets_config():
    from qoresence.cli import create_config_from_args

    class Args(SimpleNamespace):
        def __getattr__(self, name):  # every other flag: unset
            return None

    base = Args(ws_host="127.0.0.1", ws_port=8765, enable_ws=False)
    assert getattr(create_config_from_args(base), "truth_feed", None) is None
    args = Args(
        ws_host="127.0.0.1",
        ws_port=8765,
        enable_ws=False,
        truth_feed=True,
        truth_feed_dir="x/y",
        truth_feed_unsigned=True,
    )
    cfg = create_config_from_args(args).truth_feed
    assert cfg.enabled and cfg.out_dir == "x/y" and cfg.sign is False


def test_stdlib_handler_serves_truth_routes(tmp_path, monkeypatch):
    import io

    from qoresence.truth.deck_routes import handle_stdlib

    monkeypatch.setattr(feed_mod, "_default_frame_stamp", lambda: LIVE)
    monkeypatch.setattr(feed_mod, "_default_input_window", lambda a, b: [])
    cfg = TruthFeedConfig(enabled=True, out_dir=str(tmp_path / "t"), sign=False)
    f = feed_mod.make_truth_feed_from_config(cfg, session_id="std-1")
    f.on_event(_event(_payload(3, 0)))
    f.step()

    class H:
        def __init__(self, path, host="127.0.0.1"):
            self.path, self.client_address, self.headers = path, (host, 5), {}
            self.wfile, self.status, self.sent = io.BytesIO(), None, {}

        def send_response(self, code):
            self.status = code

        def send_header(self, k, v):
            self.sent[k] = v

        def end_headers(self):
            pass

    try:
        h = H("/api/truth/verify")
        assert handle_stdlib(h) and h.status == 200
        assert json.loads(h.wfile.getvalue())["ok"] is True
        h = H("/api/truth/stream?limit_s=0.1")
        assert handle_stdlib(h) and h.status == 200
        assert b"event: fact" in h.wfile.getvalue()
        h = H("/api/truth/feed", host="10.0.0.9")
        assert handle_stdlib(h) and h.status == 403
        assert handle_stdlib(H("/health")) is False
    finally:
        feed_mod.stop_truth_feed()


def test_without_cryptography_falls_back_to_unsigned(tmp_path, monkeypatch):
    from qoresence.truth import signing

    monkeypatch.setattr(signing, "crypto_available", lambda: False)
    signer, why = signing.load_or_create_signer(tmp_path / "k")
    assert signer is None and why == "cryptography_missing"
    assert not (tmp_path / "k").exists()  # no key file written
    with pytest.raises(RuntimeError):
        signing.verify_signature("00" * 32, "00" * 64, b"x")
