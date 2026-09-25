"""Clip-excision pilot gate: scoring receipts against hand labels."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from qoresence.vision import clip_excise as cx
from qoresence.vision import excise_pilot as ep

REPO_ROOT = Path(__file__).resolve().parents[1]


def _receipt(tmp_path, name, spans, *, dur=30.0, model="jev-1.13.0", profile="madden_27"):
    mp4 = tmp_path / name
    mp4.write_bytes(b"x" * 64)
    rows = [
        {"id": f"s{i}", "t0_s": t0, "t1_s": t1, "decision": d, "reason": "test", "user": None}
        for i, (t0, t1, d) in enumerate(spans)
    ]
    receipt = cx.refresh_receipt(
        {
            "schema": cx.RECEIPT_SCHEMA,
            "policy_version": cx.POLICY_VERSION,
            "referee": "jev" if model else "offline_triple_proof",
            "model": model,
            "game_profile": profile,
            "source": name,
            "source_duration_s": dur,
            "spans": rows,
            "licenses_digits": False,
        }
    )
    cx.write_receipt(mp4, receipt)
    return mp4, receipt


def _health(tmp_path, *ages):
    p = tmp_path / f"health_{'_'.join(str(a) for a in ages)}.jsonl"
    p.write_text(
        "\n".join(json.dumps({"health": {"state": {"video": {"age_s": a}}}}) for a in ages),
        encoding="utf-8",
    )
    return p


GOOD_DEAD = [[5.0, 12.0, "pause"], [15.0, 19.0, "menu"], [22.0, 27.0, "loading"]]
GOOD_SPANS = [(5.0, 12.0, "cut"), (15.0, 19.0, "cut"), (22.0, 27.0, "suggest")]


def test_score_clip_over_and_under_cut(tmp_path):
    _mp4, receipt = _receipt(tmp_path, "a.mp4", [(5.0, 12.0, "cut")])
    ok = ep.score_clip(receipt, {"dead": [[5.0, 12.0, "pause"]]})
    assert ok["over_cut_s"] == 0.0 and ok["under_cut_s"] == 0.8 and ok["cut_s"] == 6.2
    bad = ep.score_clip(receipt, {"dead": [[5.0, 9.0, "pause"]]})
    assert bad["over_cut_s"] == 2.5
    live = ep.score_clip(receipt, {"dead": []})
    assert live["over_cut_s"] == 6.2


def test_score_uses_policy_cuts_not_gamer_overrides(tmp_path):
    _mp4, receipt = _receipt(tmp_path, "a.mp4", [(5.0, 12.0, "keep")])
    receipt["spans"][0]["user"] = "cut"
    assert ep.system_cuts(receipt) == []
    assert ep.score_clip(receipt, {"dead": []})["over_cut_s"] == 0.0


def test_label_stats_latest_click_vetoes_and_accepts():
    rows = [
        {"source": "a.mp4", "span_id": "s0", "system": "suggest", "user": "keep"},
        {"source": "a.mp4", "span_id": "s0", "system": "suggest", "user": "cut"},
        {"source": "b.mp4", "span_id": "s0", "system": "suggest", "user": "keep"},
        {"source": "c.mp4", "span_id": "s1", "system": "cut", "user": "keep", "reason": "r"},
        {"source": "d.mp4", "span_id": "s0", "system": "keep", "user": "cut"},
    ]
    st = ep.label_stats(rows)
    assert st["clicks"] == 5 and st["spans_decided"] == 4
    assert st["suggestions_decided"] == 2 and st["suggest_accept_rate"] == 0.5
    assert st["vetoes"] == [{"source": "c.mp4", "span_id": "s1", "reason": "r"}]
    assert st["rescues"] == 1


def test_health_ages_reads_snapshot_raw_and_jsonl(tmp_path):
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps({"health": {"state": {"video": {"age_s": 0.2}}}}))
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"state": {"video": {"age_s": 0.4}}}))
    junk = tmp_path / "junk.json"
    junk.write_text("not json")
    ages = ep.health_ages([snap, raw, junk, tmp_path / "missing.json", _health(tmp_path, 0.1)])
    assert ages == [0.2, 0.4, 0.1]


def test_evaluate_pass_needs_every_leg(tmp_path):
    _receipt(tmp_path, "a.mp4", GOOD_SPANS)
    labels = {"a.mp4": {"profile": "madden_27", "dead": GOOD_DEAD}}
    r = ep.evaluate(tmp_path, labels, health_files=[_health(tmp_path, 0.3, 0.5)], min_clips=1)
    assert r["verdict"] == "pass", r
    assert r["summary"]["over_cut_s"] == 0.0 and r["summary"]["age_s_max"] == 0.5
    assert r["licenses_digits"] is False


def test_evaluate_fails_closed(tmp_path):
    health = [_health(tmp_path, 0.3)]
    _receipt(tmp_path, "a.mp4", GOOD_SPANS)
    over = {"a.mp4": {"profile": "madden_27", "dead": [[5.0, 8.0, "pause"]] + GOOD_DEAD[1:]}}
    r = ep.evaluate(tmp_path, over, health_files=health, min_clips=1)
    assert r["verdict"] == "fail" and "over_cut" in r["failures"][0]

    good = {"a.mp4": {"profile": "madden_27", "dead": GOOD_DEAD}}
    slow = ep.evaluate(tmp_path, good, health_files=[_health(tmp_path, 1.4)], min_clips=1)
    assert slow["verdict"] == "fail" and "age_s" in slow["failures"][0]

    drift = ep.evaluate(tmp_path, good, health_files=health, pinned_model="jev-1.14.0", min_clips=1)
    assert drift["verdict"] == "fail" and "unpinned" in drift["failures"][0]

    cx.append_label(
        tmp_path / "a.mp4",
        {"source": "a.mp4", "span_id": "s0", "system": "cut", "user": "keep"},
    )
    veto = ep.evaluate(tmp_path, good, health_files=health, min_clips=1)
    assert veto["verdict"] == "fail" and "vetoed" in veto["failures"][0]


def test_evaluate_insufficient_without_enough_evidence(tmp_path):
    _receipt(tmp_path, "a.mp4", [(5.0, 12.0, "cut")])
    _receipt(tmp_path, "v.mp4", [(5.0, 12.0, "cut")], profile="valorant")
    labels = {
        "a.mp4": {"profile": "madden_27", "dead": [[5.0, 12.0, "pause"]]},
        "v.mp4": {"profile": "valorant", "dead": [[5.0, 12.0, "pause"]]},
        "gone.mp4": {"profile": "madden_27", "dead": [[1.0, 3.0, "menu"]]},
    }
    r = ep.evaluate(tmp_path, labels)
    assert r["verdict"] == "insufficient"
    gaps = " | ".join(r["gaps"])
    assert "1/20 football clips" in gaps
    assert "no labelled menu, loading" in gaps
    assert "1 labelled clip(s) have no receipt" in gaps
    assert "no /health samples" in gaps
    assert r["missing_receipts"] == ["gone.mp4"]


def test_load_labels_drops_malformed_rows(tmp_path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps({"clips": {"a.mp4": {"dead": [[1, 3, "pause"], [5, 4], "x", [7, 9]]}}}))
    assert ep.load_labels(p) == {
        "a.mp4": {"profile": None, "dead": [[1.0, 3.0, "pause"], [7.0, 9.0, "dead"]]}
    }


def _script():
    spec = importlib.util.spec_from_file_location(
        "excise_pilot_gate", REPO_ROOT / "scripts" / "excise_pilot_gate.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_script_init_labels_and_exit_codes(tmp_path):
    gate = _script()
    _receipt(tmp_path, "a.mp4", GOOD_SPANS)
    labels = tmp_path / "labels.json"
    assert gate.main(["--clips", str(tmp_path), "--init-labels", str(labels)]) == 0
    tpl = json.loads(labels.read_text())
    assert tpl["clips"]["a.mp4"]["dead"] == [] and tpl["clips"]["a.mp4"]["profile"] == "madden_27"
    assert gate.main(["--clips", str(tmp_path), "--init-labels", str(labels)]) == 2

    out = tmp_path / "report.json"
    assert gate.main(["--clips", str(tmp_path), "--labels", str(labels), "--out", str(out)]) == 1
    assert json.loads(out.read_text())["verdict"] == "fail"

    labels.write_text(json.dumps({"clips": {"a.mp4": {"profile": "madden_27", "dead": GOOD_DEAD}}}))
    args = ["--clips", str(tmp_path), "--labels", str(labels), "--out", str(out)]
    assert gate.main(args) == 2
    health = str(_health(tmp_path, 0.2))
    assert gate.main(args + ["--min-clips", "1", "--health", health]) == 0
