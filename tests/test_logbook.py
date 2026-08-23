"""Phase 4 Logbook — session-end debrief. Default OFF. No live bus."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest


def test_logbook_default_off():
    from qoresence.foundry.logbook import is_enabled

    assert is_enabled() is False
    assert is_enabled(None) is False
    assert is_enabled(False) is False


def test_write_debrief_from_fixture_jsonl_and_chapters(tmp_path: Path):
    events = tmp_path / "events.jsonl"
    rows = [
        {"kind": "fast_chat", "message": "heat", "clock_ns": 1_000},
        {"kind": "confirm_score", "message": "14-7", "clock_ns": 2_000},
        {"lobe": "visual", "type": "scoreboard", "home": 14, "away": 7},
    ]
    events.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    clips = tmp_path / "clips"
    clips.mkdir()
    (clips / "hdmi_clip_demo.chapters.json").write_text(
        json.dumps(
            {
                "duration_s": 8.0,
                "chapters": [
                    {"t_s": 1.2, "label": "arm", "kind": "arm"},
                    {"t_s": 4.0, "label": "touchdown", "kind": "confirm_score"},
                ],
                "why": {"line": "path=confirm · 14-7"},
            }
        ),
        encoding="utf-8",
    )

    from qoresence.foundry.logbook import write_debrief

    md, payload = write_debrief(events_jsonl=events, clips_dir=clips)
    assert md.is_file()
    assert md.parent in (events.parent, clips)
    text = md.read_text(encoding="utf-8")
    assert "Logbook" in text or "debrief" in text.lower()
    assert "touchdown" in text
    assert "confirm_score" in text
    assert payload["event_count"] == 3
    assert payload["chapter_count"] == 2
    assert payload["clip_stems"] == ["hdmi_clip_demo"]
    js = md.with_suffix(".json")
    assert js.is_file()
    assert json.loads(js.read_text(encoding="utf-8"))["event_count"] == 3


def test_logbook_source_never_touches_live_bus():
    from qoresence.foundry import logbook

    src = Path(logbook.__file__).read_text(encoding="utf-8")
    assert "RetinaEventBus" not in src
    assert "subscribe" not in src
    assert "emit_raw" not in src
    assert "emit(" not in src
    tree = ast.parse(src)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("event" in (m or "") and "bus" in (m or "") for m in imported)
    assert not any((m or "").endswith(".bus") for m in imported)


def test_cli_logbook_flag_default_off_and_one_shot(tmp_path: Path, monkeypatch):
    events = tmp_path / "events.jsonl"
    events.write_text(json.dumps({"kind": "arm", "message": "snap"}) + "\n", encoding="utf-8")
    clips = tmp_path / "clips"
    clips.mkdir()

    import sys

    from qoresence import cli

    parser = cli.build_parser() if hasattr(cli, "build_parser") else None
    if parser is None:
        pytest.fail("cli.build_parser missing — --logbook must be a default-OFF flag")
    ns = parser.parse_args([])
    assert getattr(ns, "logbook", None) is False

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "qoresence",
            "--logbook",
            "--jsonl-path",
            str(events),
        ],
    )
    monkeypatch.setenv("QORESENCE_CLIPS_DIR", str(clips))
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    written = list(tmp_path.rglob("logbook_*")) + list(tmp_path.rglob("*debrief*"))
    assert written, "one-shot --logbook must write a debrief next to the session"
