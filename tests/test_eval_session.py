"""Phase 6 tests for eval/eval_session.py replay metrics."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from eval.eval_session import eval_session


def _make_session_jsonl(path: Path, visual_events: list[dict]) -> None:
    """Write a minimal session JSONL for eval testing."""
    session_id = "test_session"
    head_ns = 1_000_000_000
    clock_ns = head_ns
    lines = []

    # Session start from a lobe so the fusion engine has some state to work with.
    lines.append(
        json.dumps(
            {
                "session_id": session_id,
                "clock_ns": clock_ns,
                "session_head_ns": head_ns,
                "source_lobe": "streamer",
                "type": "session_start",
                "payload": {"source_kind": "test"},
            }
        )
    )

    for ev in visual_events:
        clock_ns += 100_000_000
        lines.append(
            json.dumps(
                {
                    "session_id": session_id,
                    "clock_ns": clock_ns,
                    "session_head_ns": head_ns,
                    "source_lobe": "visual",
                    "type": "visual_context",
                    "payload": {
                        "game_category": ev["category"],
                        "game_state": ev["state"],
                        "confidence": ev["confidence"],
                        "latency_ms": ev["latency_ms"],
                    },
                }
            )
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_eval_session_passes_for_football_only():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "session.jsonl"
        _make_session_jsonl(
            path,
            [
                {"category": "football", "state": "gameplay", "confidence": 0.8, "latency_ms": 10.0},
                {"category": "football", "state": "gameplay", "confidence": 0.9, "latency_ms": 12.0},
                {"category": "football", "state": "gameplay", "confidence": 0.85, "latency_ms": 8.0},
                {"category": "unknown", "state": "menu", "confidence": 0.4, "latency_ms": 5.0},
            ],
        )

        result = eval_session(path)
        assert result["shooter_found"] == 0
        assert result["football_precision"] == 1.0
        assert result["avg_vlm_latency_ms"] < 100.0
        assert result["passed"] is True


def test_eval_session_fails_when_shooter_present():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "session.jsonl"
        _make_session_jsonl(
            path,
            [
                {"category": "football", "state": "gameplay", "confidence": 0.8, "latency_ms": 10.0},
                {"category": "shooter", "state": "gameplay", "confidence": 0.8, "latency_ms": 9.0},
            ],
        )

        result = eval_session(path)
        assert result["shooter_found"] == 1
        assert result["football_precision"] < 1.0
        assert result["passed"] is False
