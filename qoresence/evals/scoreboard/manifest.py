"""Score-replay manifest: observation stream + ground-truth timeline.

Schema ``qoresence-score-replay-0``::

    {
      "schema": "qoresence-score-replay-0",
      "session_id": "fixture-or-recorded-session",
      "game_profile": "cfb_27",
      "truth": [
        {"start_ns": 0, "home_score": 7, "away_score": 3, "readable": true}
      ],
      "observations": [
        {
          "frame_seq": 101, "captured_ns": 6000000000,
          "session_id": "session-x", "crop_hash": "crop-abc",
          "home_team": "LOU", "away_team": "NCST",
          "home_score": 7, "away_score": 3,
          "scene": "gameplay", "quarter": 1, "game_clock": "12:34",
          "arrival_delay_ns": 0,
          "jev": {"implausible_noul": 0.12, "jump_kind": "legal_score"}
        }
      ]
    }

``truth`` is a piecewise-constant timeline: each segment applies from its
``start_ns`` until the next segment. ``readable: false`` marks screens where a
person could not verify the board (blur, replay wipe, ticker) — exposure during
those segments is scored as ambiguous, never as incorrect.

``observations`` are what the seeing path parsed (right or wrong), bound to the
source frame's seq/clock. ``arrival_delay_ns`` models VLM latency: an
observation is evaluated at ``captured_ns + arrival_delay_ns`` and counts stale
past the confirm window. ``jev`` carries a TypeSafe verdict for the
prior→candidate transition — recorded live when ``QORESENCE_JEV`` is on (the
VLM worker asks Jev on each changed same-identity pair and stores the verdict
on the row); fixtures may also hand-author it as hypothetical input.

Recorded sessions: ``QORESENCE_SCORE_REPLAY_LOG=<path>`` makes the scoreboard
VLM append each surviving parse (plus ``_observation`` source metadata) as one
JSONL row. ``build_manifest_from_recording`` folds those rows plus a
hand-labeled truth file into this schema.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from qoresence.vision.score_recheck import BoardObservation

MANIFEST_SCHEMA = "qoresence-score-replay-0"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def load_manifest(path: Path | str) -> dict[str, Any]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"unsupported score-replay schema in {path}")
    truth = [
        {
            "start_ns": int(seg.get("start_ns") or 0),
            "home_score": seg.get("home_score"),
            "away_score": seg.get("away_score"),
            "readable": bool(seg.get("readable", True)),
        }
        for seg in raw.get("truth") or []
    ]
    truth.sort(key=lambda s: s["start_ns"])
    observations = [dict(o) for o in raw.get("observations") or []]
    observations.sort(key=lambda o: int(o.get("captured_ns") or 0))
    end_ns = raw.get("end_ns")
    if end_ns is None:
        ends = [int(o.get("captured_ns") or 0) for o in observations]
        ends += [s["start_ns"] for s in truth]
        end_ns = (max(ends) + 1_000_000_000) if ends else 0
    return {
        "path": str(path),
        "session_id": str(raw.get("session_id") or "session"),
        "game_profile": str(raw.get("game_profile") or ""),
        "truth": truth,
        "observations": observations,
        "end_ns": int(end_ns),
    }


def discover_manifests(directory: Path | str | None = None) -> list[Path]:
    root = Path(directory) if directory else FIXTURE_DIR
    return sorted(root.glob("*.json"))


def to_board(row: dict[str, Any]) -> BoardObservation:
    def _i(v: Any) -> int:
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    return BoardObservation(
        session_id=str(row.get("session_id") or ""),
        frame_seq=_i(row.get("frame_seq")),
        captured_ns=_i(row.get("captured_ns")),
        crop_hash=str(row.get("crop_hash") or ""),
        home_team=str(row.get("home_team") or ""),
        away_team=str(row.get("away_team") or ""),
        home_score=row.get("home_score"),
        away_score=row.get("away_score"),
        scene=str(row.get("scene") or ""),
        quarter=row.get("quarter"),
        game_clock=row.get("game_clock"),
    )


def truth_at(truth: list[dict[str, Any]], ns: int) -> dict[str, Any] | None:
    """Segment covering ``ns`` — the last one whose start_ns <= ns."""
    seg = None
    for s in truth:
        if s["start_ns"] <= ns:
            seg = s
        else:
            break
    return seg


def truth_pair_at(truth: list[dict[str, Any]], ns: int) -> tuple[int | None, int | None] | None:
    seg = truth_at(truth, ns)
    if seg is None:
        return None
    return seg.get("home_score"), seg.get("away_score")


def build_manifest_from_recording(
    recording_jsonl: Path | str,
    *,
    truth: list[dict[str, Any]],
    session_id: str = "",
    game_profile: str = "",
    out_path: Path | str | None = None,
) -> dict[str, Any]:
    """Fold a QORESENCE_SCORE_REPLAY_LOG JSONL + labeled truth into a manifest."""
    observations: list[dict[str, Any]] = []
    for line in Path(recording_jsonl).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        src = row.get("_observation") or {}
        captured = int(src.get("clock_ns") or 0)
        recorded = int(row.get("recorded_ns") or captured)
        observations.append(
            {
                "frame_seq": src.get("seq"),
                "captured_ns": captured,
                "session_id": src.get("session_id"),
                "crop_hash": src.get("crop_hash"),
                "home_team": row.get("home_team") or row.get("left_team"),
                "away_team": row.get("away_team") or row.get("right_team"),
                "home_score": row.get("home_score"),
                "away_score": row.get("away_score"),
                "scene": src.get("game_state"),
                "quarter": row.get("quarter"),
                "game_clock": row.get("clock"),
                "arrival_delay_ns": max(0, recorded - captured),
                "analyzed_crop_hash": src.get("analyzed_crop_hash"),
                "jev": row.get("jev"),
            }
        )
    ends = [int(o.get("captured_ns") or 0) for o in observations]
    ends += [int(s.get("start_ns") or 0) for s in truth]
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "session_id": session_id or str(
            observations[0].get("session_id") or "recorded"
            if observations else "recorded"
        ),
        "game_profile": game_profile,
        "truth": sorted(truth, key=lambda s: int(s.get("start_ns") or 0)),
        "observations": observations,
        "end_ns": (max(ends) + 5_000_000_000) if ends else 0,
    }
    if out_path is not None:
        Path(out_path).write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    return manifest
