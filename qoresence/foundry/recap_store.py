"""Per-session Recap on disk. Rebuild from jsonl. Persist loop is default OFF.

Off the grab loop. No QorAct import. Recap stays readable after Deck is down.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qoresence.foundry.narrative_engine import generate_narrative
from qoresence.foundry.session_view import normalize_pack, recap_from_envelope

log = logging.getLogger(__name__)

PERSIST_ENV = "QORESENCE_RECAP_PERSIST"
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSONL = _REPO_ROOT / "logs" / "civif" / "session.jsonl"
DEFAULT_AUDITS = _REPO_ROOT / "audits"
STOP_TAIL_BYTES = 32_000_000

_loop_stop = threading.Event()
_loop_thread: threading.Thread | None = None
_win_handler_ref = None
_atexit_sid = ""


def persist_enabled(environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    return str(env.get(PERSIST_ENV, "")).strip().lower() in {"1", "true", "on"}


def _iso_z(now: datetime | None = None) -> str:
    stamp = now or datetime.now(UTC)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=UTC)
    return stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iter_session_ticks(
    jsonl_path: Path | str,
    session_id: str,
    *,
    tail_bytes: int | None = None,
):
    """Stream ticks for one session. Skip other lines without full parse when possible."""
    path = Path(jsonl_path)
    sid = str(session_id or "")
    if not sid or not path.is_file():
        return
    needle = sid.encode("utf-8")
    with path.open("rb") as fh:
        if tail_bytes is not None and tail_bytes > 0:
            try:
                size = path.stat().st_size
                fh.seek(max(0, size - int(tail_bytes)))
                if fh.tell() > 0:
                    fh.readline()
            except Exception:
                fh.seek(0)
        for raw in fh:
            if needle not in raw:
                continue
            try:
                row = json.loads(raw)
            except Exception:
                continue
            if not isinstance(row, dict):
                continue
            if str(row.get("session_id") or "") != sid:
                continue
            yield row


def recap_from_ticks(session_id: str, ticks: list[dict[str, Any]]) -> dict[str, Any]:
    sid = str(session_id or "")
    nar = generate_narrative(sid, ticks=list(ticks), persist=False, session_persisted=True)
    view = normalize_pack({**nar, "persisted": True})
    now = _iso_z()
    last_at = None
    events = view.get("events") or []
    if events:
        last_at = events[-1].get("timestamp")
    return recap_from_envelope(
        {
            "ok": True,
            "status": "live" if events else "empty",
            "session": sid,
            "view": view,
            "freshness": {
                "generated_at": now,
                "last_event_at": last_at,
                "age_ms": 0,
                "stale": False,
            },
        }
    )


def recap_from_jsonl(
    jsonl_path: Path | str,
    session_id: str,
    *,
    tail_bytes: int | None = None,
) -> dict[str, Any]:
    ticks = list(iter_session_ticks(jsonl_path, session_id, tail_bytes=tail_bytes))
    return recap_from_ticks(session_id, ticks)


def recap_path_for(session_id: str, audits_dir: Path | str | None = None) -> Path:
    root = Path(audits_dir) if audits_dir is not None else DEFAULT_AUDITS
    sid = str(session_id or "session")
    return root / f"session-recap-{sid}.json"


def write_session_recap(
    recap: dict[str, Any],
    dest: Path | str | None = None,
    *,
    enabled: bool | None = None,
) -> Path | None:
    """Fail-open write. Returns path or None. Does not spawn QorAct."""
    on = persist_enabled() if enabled is None else bool(enabled)
    if not on:
        return None
    try:
        sid = str(recap.get("session") or recap.get("session_id") or "session")
        path = Path(dest) if dest is not None else recap_path_for(sid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(recap, indent=2) + "\n", encoding="utf-8")
        return path if path.is_file() else None
    except Exception:
        return None


def persist_recap_at_stop(
    *,
    session_id: str,
    jsonl_path: Path | str | None = None,
    dest: Path | str | None = None,
) -> dict[str, Any]:
    """D-PERSIST stop-once: write Recap from jsonl tail. Env unset still writes. No door.

    Tail-scan so Windows CTRL_CLOSE (~5s) still finishes. Full salvage uses rebuild_and_write.
    """
    try:
        try:
            from qoresence.foundry.cer_log import get_cer_log

            get_cer_log().flush(timeout=1.5)
        except Exception:
            pass
        sid = str(session_id or "").strip()
        if not sid:
            log.info("recap_stop miss reason=no_session")
            return {"recap": {}, "path": None, "spawned": False, "reason": "no_session"}
        src = Path(jsonl_path) if jsonl_path is not None else DEFAULT_JSONL
        if not src.is_file():
            log.info("recap_stop miss reason=no_jsonl")
            return {"recap": {}, "path": None, "spawned": False, "reason": "no_jsonl"}
        recap = recap_from_jsonl(src, sid, tail_bytes=STOP_TAIL_BYTES)
        out = Path(dest) if dest is not None else recap_path_for(sid)
        path = write_session_recap(recap, out, enabled=True)
        if path is None:
            log.info("recap_stop miss reason=write_failed")
            return {"recap": recap, "path": None, "spawned": False, "reason": "write_failed"}
        log.info("recap_stop path=%s events=%s", path, recap.get("event_count"))
        return {"recap": recap, "path": str(path), "spawned": False}
    except Exception as exc:
        log.info("recap_stop miss reason=%s", type(exc).__name__)
        return {"recap": {}, "path": None, "spawned": False, "reason": type(exc).__name__}


def install_recap_stop_hooks(session_id: str) -> None:
    """atexit + Windows console close write Recap before the process is killed."""
    global _win_handler_ref, _atexit_sid
    sid = str(session_id or "").strip()
    if not sid:
        return
    _atexit_sid = sid

    def _write() -> None:
        persist_recap_at_stop(session_id=_atexit_sid or sid)

    atexit.register(_write)
    if sys.platform != "win32":
        return
    try:
        import ctypes

        Handler = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

        def _handler(ctrl_type: int) -> int:
            _write()
            return 1

        _win_handler_ref = Handler(_handler)
        ctypes.windll.kernel32.SetConsoleCtrlHandler(_win_handler_ref, 1)
    except Exception:
        return


def rebuild_and_write(
    *,
    session_id: str,
    jsonl_path: Path | str | None = None,
    dest: Path | str | None = None,
    persist_enabled: bool = True,
) -> dict[str, Any]:
    """Rebuild Recap from jsonl and write it. persist_enabled True for salvage."""
    recap = recap_from_jsonl(jsonl_path or DEFAULT_JSONL, session_id)
    path = write_session_recap(recap, dest or recap_path_for(session_id), enabled=persist_enabled)
    return {"recap": recap, "path": str(path) if path else None}


def _loop_body(*, interval_s: float, jsonl_path: Path, audits_dir: Path) -> None:
    from qoresence.core.session import SessionAuthority

    while not _loop_stop.wait(interval_s):
        try:
            ident = SessionAuthority.current()
            sid = str(ident.session_id or "") if ident is not None else ""
            if not sid:
                continue
            recap = recap_from_jsonl(jsonl_path, sid)
            write_session_recap(recap, recap_path_for(sid, audits_dir), enabled=True)
        except Exception:
            continue


def start_recap_persist_loop(
    *,
    interval_s: float = 5.0,
    jsonl_path: Path | str | None = None,
    audits_dir: Path | str | None = None,
) -> bool:
    """Daemon loop. No-op unless QORESENCE_RECAP_PERSIST=1. Never raises."""
    global _loop_thread
    try:
        if not persist_enabled():
            return False
        if _loop_thread is not None and _loop_thread.is_alive():
            return True
        _loop_stop.clear()
        _loop_thread = threading.Thread(
            target=_loop_body,
            kwargs={
                "interval_s": max(1.0, float(interval_s)),
                "jsonl_path": Path(jsonl_path or DEFAULT_JSONL),
                "audits_dir": Path(audits_dir or DEFAULT_AUDITS),
            },
            name="recap-persist",
            daemon=True,
        )
        _loop_thread.start()
        log.info("Recap persist loop on (interval=%.1fs, default-OFF gate open)", interval_s)
        return True
    except Exception:
        return False


def stop_recap_persist_loop() -> None:
    _loop_stop.set()
