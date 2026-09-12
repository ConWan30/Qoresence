"""Run observation eval fixture packs offline — no Quicksilver/VLM."""

from __future__ import annotations

import json
from pathlib import Path

from qoresence.observation.lifecycle import parse_journal_row

from .metrics import EvalMetrics, compute_metrics

FIXTURE_SCHEMA = "qoresence-observation-eval-0"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema") != FIXTURE_SCHEMA:
        raise ValueError(f"unsupported eval fixture schema in {path}")
    rows = [parse_journal_row(row) for row in raw.get("journal") or []]
    return {
        "path": str(path),
        "session_id": str(raw.get("session_id") or "session"),
        "labels": dict(raw.get("labels") or {}),
        "rows": rows,
    }


def run_fixture(path: Path) -> EvalMetrics:
    fixture = load_fixture(path)
    return compute_metrics(
        fixture["rows"],
        session_id=fixture["session_id"],
        labels=fixture["labels"],
    )


def discover_fixtures(directory: Path | None = None) -> list[Path]:
    root = directory or FIXTURE_DIR
    return sorted(root.glob("*.json"))


def run_all(directory: Path | None = None) -> list[EvalMetrics]:
    return [run_fixture(path) for path in discover_fixtures(directory)]
