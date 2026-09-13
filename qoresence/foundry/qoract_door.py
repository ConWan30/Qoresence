"""Optional stop-hook spawn of QorAct issue_from_recap.py.

Default OFF (QORESENCE_QORACT_DOOR unset). Subprocess only. Never imports
qoract. Never raises into the stop path. Recap write is independent of the door.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

DOOR_ENV = "QORESENCE_QORACT_DOOR"
ROOT_ENV = "QORESENCE_QORACT_ROOT"
DEFAULT_TIMEOUT_S = 8.0


def door_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get(DOOR_ENV, "")).strip().lower() in {"1", "true", "on"}


def write_recap_file(path: Path | str, recap: dict[str, Any]) -> bool:
    """Fail-open Recap persist. Returns False instead of raising."""
    try:
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(recap, indent=2) + "\n", encoding="utf-8")
        return dest.is_file()
    except Exception:
        return False


def _qoract_script(qoract_root: Path | str | None) -> Path | None:
    if qoract_root is not None:
        script = Path(qoract_root) / "scripts" / "issue_from_recap.py"
        return script if script.is_file() else None
    roots: list[Path] = []
    env_root = os.environ.get(ROOT_ENV, "").strip()
    if env_root:
        roots.append(Path(env_root))
    here = Path(__file__).resolve()
    roots.append(here.parents[2].parent / "QorAct")
    roots.append(Path.home() / "QorAct")
    seen: set[Path] = set()
    for root in roots:
        try:
            root = root.resolve()
        except OSError:
            continue
        if root in seen:
            continue
        seen.add(root)
        script = root / "scripts" / "issue_from_recap.py"
        if script.is_file():
            return script
    return None


def maybe_spawn_qoract_door(
    recap_path: Path | str,
    *,
    recap: dict[str, Any] | None = None,
    qoract_root: Path | str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    spawn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Spawn issue_from_recap.py when enabled. Never raises."""
    try:
        if not door_enabled():
            return {"spawned": False, "reason": "disabled"}
        script = _qoract_script(qoract_root)
        if script is None:
            return {"spawned": False, "reason": "missing_script"}
        recap_path = Path(recap_path)
        session = ""
        if isinstance(recap, dict):
            session = str(recap.get("session") or recap.get("session_id") or "")
        out_name = f"qoract_{session or recap_path.stem}.json"
        out_path = recap_path.parent / out_name
        cmd = [
            sys.executable,
            str(script),
            "--recap",
            str(recap_path),
            "--out",
            str(out_path),
        ]
        run = spawn if spawn is not None else subprocess.run
        run(
            cmd,
            timeout=float(timeout_s),
            check=False,
            capture_output=True,
        )
        return {"spawned": True, "reason": "ok"}
    except Exception:
        return {"spawned": True, "reason": "fail_open"}


def persist_and_maybe_door(
    *,
    recap: dict[str, Any],
    recap_path: Path | str,
    qoract_root: Path | str | None = None,
    spawn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Write Recap first, then optional door. Recap survives a dead door."""
    try:
        wrote = write_recap_file(recap_path, recap)
        door = maybe_spawn_qoract_door(
            recap_path,
            recap=recap,
            qoract_root=qoract_root,
            spawn=spawn,
        )
        return {
            "wrote": bool(wrote),
            "spawned": bool(door.get("spawned")),
            "reason": str(door.get("reason") or ""),
        }
    except Exception:
        return {"wrote": False, "spawned": False, "reason": "fail_open"}


def persist_live_session_recap(
    *,
    session_id: str = "",
    recap_path: Path | str | None = None,
) -> dict[str, Any]:
    """Stop-path helper. Builds Recap, writes it, maybe spawns. Never raises."""
    try:
        from qoresence.foundry.session_view import build_session_recap

        recap = build_session_recap(session_id=session_id)
        sid = str(session_id or recap.get("session") or "session")
        dest = Path(recap_path) if recap_path is not None else Path("audits") / f"session-recap-{sid}.json"
        return persist_and_maybe_door(recap=recap, recap_path=dest)
    except Exception:
        return {"wrote": False, "spawned": False, "reason": "fail_open"}
