#!/usr/bin/env python3
"""Frame License Bureau v0 — export helper (observation plane only).

Reads stamped SEQGATE memory / fixture JSONL and emits:
  - license-pack-v0.jsonl  (kind=license | kind=manifest)
  - notary.jsonl           (kind=notary for hold / refuse / speech attempts)

Fail-closed: rows without seqgate stamp are refused (notary reason=unstamped),
never invented into licensed speech. Digits are never filled in.

CLI: ``python -m qoresence.license_bureau`` or ``scripts/export_license_pack.py``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "frame-license-bureau/v0"
PRODUCT = "Frame License Bureau"


def _is_stamped(row: dict[str, Any]) -> bool:
    return "seqgate" in row and row.get("seqgate") in ("licensed", "hold")


def _license_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "license",
        "schema": SCHEMA,
        "clock_ns": row.get("clock_ns"),
        "frame_seq": row.get("frame_seq"),
        "crop_hash": row.get("crop_hash"),
        "path": row.get("path"),
        "ticket_id": row.get("ticket_id"),
        "seqgate": row.get("seqgate"),
        "reason": row.get("reason"),
        "plane": "observation",
        "case": row.get("case"),
    }


def _notary_row(
    row: dict[str, Any],
    *,
    seqgate: str,
    reason: str,
    attempt: str,
) -> dict[str, Any]:
    return {
        "kind": "notary",
        "schema": SCHEMA,
        "clock_ns": row.get("clock_ns"),
        "frame_seq": row.get("frame_seq"),
        "seqgate": seqgate,
        "reason": reason,
        "attempt": attempt,
        "case": row.get("case"),
        "plane": "observation",
    }


def export_rows(
    rows: list[dict[str, Any]],
    *,
    session_id: str,
    tip_sha: str,
    sku: str = "A",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (pack_lines, notary_lines). Pack starts with manifest."""
    pack: list[dict[str, Any]] = [
        {
            "kind": "manifest",
            "product": PRODUCT,
            "schema": SCHEMA,
            "sku": sku,
            "session_id": session_id,
            "tip_sha": tip_sha,
            "density_gate": "pending",
            "monetize": False,
        }
    ]
    notary: list[dict[str, Any]] = []

    for row in rows:
        case = row.get("case") or ""

        if not _is_stamped(row):
            # Fail-closed: never promote unstamped to license.
            notary.append(
                _notary_row(
                    row,
                    seqgate="hold",
                    reason="unstamped",
                    attempt="write" if "write" in case else "speech",
                )
            )
            continue

        seq = row.get("seqgate")
        reason = row.get("reason") or ("licensed" if seq == "licensed" else "hold")

        # Speech freshness: live_* mismatch → hold notary, no license promotion.
        if "live_frame_seq" in row or "live_clock_ns" in row:
            live_seq = row.get("live_frame_seq")
            stamp_seq = row.get("frame_seq")
            expect_ok = row.get("expect_licensed")
            fresh = live_seq == stamp_seq
            if expect_ok is False or not fresh:
                notary.append(
                    _notary_row(
                        row,
                        seqgate="hold",
                        reason="ticket_stale" if not fresh else (reason or "hold"),
                        attempt="speech",
                    )
                )
                # Still record the underlying stamp as license history when stamped licensed.
                if seq == "licensed":
                    pack.append(_license_row(row))
                elif seq == "hold":
                    pack.append(_license_row(row))
                    notary.append(
                        _notary_row(row, seqgate="hold", reason=reason, attempt="write")
                    )
                continue

            if expect_ok is True or (fresh and seq == "licensed"):
                pack.append(_license_row(row))
                notary.append(
                    _notary_row(
                        row,
                        seqgate="licensed",
                        reason="licensed",
                        attempt="speech",
                    )
                )
                continue

        # Write / stamp-only rows
        pack.append(_license_row(row))
        if seq == "hold":
            notary.append(
                _notary_row(row, seqgate="hold", reason=reason, attempt="write")
            )
        else:
            notary.append(
                _notary_row(
                    row, seqgate="licensed", reason=reason or "licensed", attempt="write"
                )
            )

    return pack, notary


def write_jsonl(path: Path, lines: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in lines:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"bad JSONL {path}:{i}: {e}") from e
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", "-i", required=True, type=Path)
    p.add_argument("--out-dir", "-o", required=True, type=Path)
    p.add_argument("--session-id", default="fixture")
    p.add_argument("--tip-sha", default="9d78c37")
    p.add_argument("--sku", default="A", choices=["A", "B", "C"])
    args = p.parse_args(argv)

    rows = load_jsonl(args.input)
    pack, notary = export_rows(
        rows, session_id=args.session_id, tip_sha=args.tip_sha, sku=args.sku
    )

    # Guard: no license row without seqgate stamp field
    for line in pack:
        if line.get("kind") == "license" and line.get("seqgate") not in (
            "licensed",
            "hold",
        ):
            raise SystemExit("fail-closed: license row missing seqgate stamp")

    out = args.out_dir
    write_jsonl(out / "license-pack-v0.jsonl", pack)
    write_jsonl(out / "notary.jsonl", notary)
    print(f"wrote {out / 'license-pack-v0.jsonl'} ({len(pack)} lines)")  # noqa: T201
    print(f"wrote {out / 'notary.jsonl'} ({len(notary)} lines)")  # noqa: T201
    print("monetize=false density_gate=pending")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
