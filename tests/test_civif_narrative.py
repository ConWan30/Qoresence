"""CIVIF Layer 3 narrative + dataset — fail-closed observation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from qoresence.core.coupled_event import build_coupling_sidecar
from qoresence.foundry.dataset import write_dataset
from qoresence.foundry.narrative import narrate_clip, narrative_from_sidecar


def _side(**kw):
    base = {
        "clip_id": "hdmi_n",
        "session_id": "",
        "start_ns": 1_000_000_000,
        "end_ns": 2_000_000_000,
        "frame_start": 1,
        "frame_end": 2,
        "video_path": "hdmi_n.mp4",
        "events": [],
        "coupling": {},
        "coupling_history": [],
    }
    base.update(kw)
    return build_coupling_sidecar(**base)


def test_unbodied_narrative_withholds_timing():
    out = narrative_from_sidecar(_side())
    assert out["ok"] is True
    assert out["bodied"] is False
    assert "timing" in out["withheld"]
    assert "DualSense" in out["text"]
    assert out["timing"] is None
    assert "99" not in out["text"]


def test_bodied_narrative_includes_event_count():
    out = narrative_from_sidecar(
        _side(
            events=[
                {"clock_ns": 1_100_000_000, "name": "R2", "kind": "trigger", "hid_domain": "play"},
            ]
        )
    )
    assert out["bodied"] is True
    assert "1 bodied input" in out["text"]
    assert "timing" not in out["withheld"]


def test_dataset_jsonl_fail_closed(tmp_path):
    data = _side()
    data["situation"]["home_score"] = 77
    data["situation"]["board_locked"] = False
    (tmp_path / "hdmi_n.coupling.json").write_text(json.dumps(data), encoding="utf-8")
    dest = tmp_path / "out.jsonl"
    result = write_dataset(dest, clips_dir=tmp_path)
    assert result["count"] == 1
    row = json.loads(dest.read_text(encoding="utf-8").splitlines()[0])
    assert row["bodied"] is False
    assert row["home_score"] is None
    assert "77-77" not in row.get("search_tokens", "")


def test_narrate_clip_and_cli(tmp_path):
    p = tmp_path / "hdmi_n.coupling.json"
    p.write_text(json.dumps(_side()), encoding="utf-8")
    out = narrate_clip("hdmi_n", clips_dir=tmp_path)
    assert out["ok"] is True
    dest = tmp_path / "ds.jsonl"
    script = Path(__file__).resolve().parents[1] / "scripts" / "export_civif_dataset.py"
    r = subprocess.run(
        [sys.executable, str(script), str(tmp_path), str(dest)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert dest.is_file()
