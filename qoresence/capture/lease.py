"""Named capture lease. Second open of the same DShow device fails closed."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class CaptureLeaseError(RuntimeError):
    """Another process already owns this capture device."""


@dataclass
class CaptureLease:
    device: str
    pid: int
    owner: str
    path: str


def _lock_root(lock_dir: str | Path | None) -> Path:
    if lock_dir is not None:
        return Path(lock_dir)
    local = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "."
    return Path(local) / "Qoresence" / "leases"


def _lease_dir(device: str, lock_dir: str | Path | None) -> Path:
    slug = _SAFE.sub("_", str(device or "capture")).strip("_") or "capture"
    return _lock_root(lock_dir) / f"lease-{slug}"


def acquire_capture_lease(
    device: str,
    owner: str = "qoresence-streamer",
    *,
    lock_dir: str | Path | None = None,
) -> CaptureLease:
    """Exclusive mkdir lease. Stale dead-pid dirs are stolen."""
    d = _lease_dir(device, lock_dir)
    d.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "device": str(device),
        "pid": os.getpid(),
        "owner": str(owner),
    }
    try:
        d.mkdir()
    except FileExistsError:
        existing = _read_meta(d)
        stale_pid = int(existing.get("pid") or 0)
        if stale_pid and _pid_alive(stale_pid):
            raise CaptureLeaseError(
                f"capture lease held by pid={stale_pid} owner={existing.get('owner')} device={device}"
            )
        _rm_lease_dir(d)
        try:
            d.mkdir()
        except FileExistsError as e:
            raise CaptureLeaseError(f"capture lease busy device={device}") from e
    (d / "owner.json").write_text(json.dumps(meta), encoding="utf-8")
    return CaptureLease(
        device=str(device),
        pid=int(meta["pid"]),
        owner=str(owner),
        path=str(d),
    )


def release_capture_lease(lease: CaptureLease | None) -> None:
    if lease is None:
        return
    _rm_lease_dir(Path(lease.path))


def lease_health(
    *,
    lock_dir: str | Path | None = None,
    device: str = "USB3.0 Video",
) -> dict[str, Any]:
    d = _lease_dir(device, lock_dir)
    meta = _read_meta(d)
    pid = int(meta.get("pid") or 0)
    alive = bool(pid and _pid_alive(pid))
    return {
        "ok": alive,
        "owner": str(meta.get("owner") or ""),
        "device": str(meta.get("device") or device),
        "pid": pid if alive else 0,
        "path": str(d) if d.exists() else "",
    }


def _read_meta(d: Path) -> dict[str, Any]:
    p = d / "owner.json"
    if not p.is_file():
        return {}
    try:
        bag = json.loads(p.read_text(encoding="utf-8"))
        return bag if isinstance(bag, dict) else {}
    except Exception:
        return {}


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _rm_lease_dir(d: Path) -> None:
    try:
        for child in d.iterdir():
            try:
                child.unlink()
            except Exception:
                pass
        d.rmdir()
    except Exception:
        pass
