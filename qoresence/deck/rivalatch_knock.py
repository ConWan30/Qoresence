"""Rivalatch ship-receipt knock for Qoresence (thin, opt-in, stdlib only).

Rivalatch (VibeGate shared ship door) lodges the frozen ``gate.run`` body:

    app_ref = {type: "git", uri: "https://github.com/ConWan30/Qoresence", rev: <sha>}
    checks  = ["smoke"]   acceptance = {criteria: [], base_url_path: "/"}

The door shallow-clones the public repo at ``rev``, serves the Pages root
(``docs/``) and smokes ``GET /``. No new fields, no fourth tool.

Two surfaces, no key on either page:

* ``build_deep_link`` / ``GET /api/rivalatch/knock-link`` — Mobile Glass
  "Knock Rivalatch" share link (``rivalatch://knock?…``) for the local tip.
  Tip unknown → link is ``null`` (HOLD), never a guessed SHA.
* ``python qoresence/deck/rivalatch_knock.py lodge --sha <sha>`` — CI ship
  receipt. ``VIBEGATE_API_KEY`` absent → skip-closed (exit 0, nothing sent).
  The key is read from env only and never printed.

Runnable as a plain script (no package import) so the GitHub Action needs no
dependency install.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

DOOR_DEFAULT = "https://vibegate-production.up.railway.app"
REPO_URI = "https://github.com/ConWan30/Qoresence"
ENV_KEY = "VIBEGATE_API_KEY"
ENV_DOOR = "VIBEGATE_DOOR_URL"
SCHEME = "rivalatch"
_SHA = re.compile(r"^[0-9a-f]{40}$")


def is_full_sha(value: str | None) -> bool:
    return bool(value) and bool(_SHA.match(str(value).strip().lower()))


def idempotency_key_for(sha: str, *, surface: str) -> str:
    """Deterministic per tip + surface: re-knocking the same tip is Recalled (200)."""
    return f"qoresence-{surface}-{sha.lower()}"


def build_gate_body(sha: str, *, idempotency_key: str) -> dict[str, Any]:
    if not is_full_sha(sha):
        raise ValueError("sha must be a full 40-hex commit id")
    return {
        "app_ref": {"type": "git", "uri": REPO_URI, "rev": sha.lower()},
        "checks": ["smoke"],
        "acceptance": {"criteria": [], "base_url_path": "/"},
        "idempotency_key": idempotency_key,
    }


def build_deep_link(sha: str, *, idempotency_key: str | None = None) -> str:
    """rivalatch://knock?… — same query keys as vibegate_ship.mobile_knocker."""
    if not is_full_sha(sha):
        raise ValueError("sha must be a full 40-hex commit id")
    sha = sha.lower()
    q = {
        "idempotency_key": idempotency_key or idempotency_key_for(sha, surface="glass"),
        "type": "git",
        "uri": REPO_URI,
        "rev": sha,
        "checks": "smoke",
        "base_url_path": "/",
    }
    return f"{SCHEME}://knock?{urlencode(q, quote_via=quote)}"


# ---------------------------------------------------------------------------
# Local tip (no subprocess, no network)
# ---------------------------------------------------------------------------


def _git_dir(repo_root: Path) -> Path | None:
    dot = repo_root / ".git"
    if dot.is_dir():
        return dot
    if dot.is_file():  # worktree: "gitdir: <path>"
        text = dot.read_text(encoding="utf-8", errors="ignore").strip()
        if text.startswith("gitdir:"):
            p = Path(text.split(":", 1)[1].strip())
            p = p if p.is_absolute() else (repo_root / p)
            return p if p.is_dir() else None
    return None


def _common_dir(git_dir: Path) -> Path:
    common = git_dir / "commondir"
    if common.is_file():
        rel = common.read_text(encoding="utf-8", errors="ignore").strip()
        p = Path(rel) if Path(rel).is_absolute() else (git_dir / rel)
        if p.is_dir():
            return p
    return git_dir


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    for base in (git_dir, _common_dir(git_dir)):
        loose = base / ref
        if loose.is_file():
            val = loose.read_text(encoding="utf-8", errors="ignore").strip()
            return val.lower() if is_full_sha(val) else None
        packed = base / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.strip().split(" ", 1)
                if len(parts) == 2 and parts[1] == ref and is_full_sha(parts[0]):
                    return parts[0].lower()
    return None


def local_git_tip(repo_root: Path | None = None) -> dict[str, str | None]:
    """``{sha, ref}`` of the checkout HEAD, or ``{sha: None}`` when unknown."""
    root = repo_root or Path(__file__).resolve().parents[2]
    out: dict[str, str | None] = {"sha": None, "ref": None}
    try:
        gd = _git_dir(root)
        if gd is None:
            return out
        head = (gd / "HEAD").read_text(encoding="utf-8", errors="ignore").strip()
        if head.startswith("ref:"):
            ref = head.split(":", 1)[1].strip()
            out["ref"] = ref
            out["sha"] = _resolve_ref(gd, ref)
        elif is_full_sha(head):
            out["sha"] = head.lower()
    except OSError:
        return {"sha": None, "ref": None}
    return out


def knock_link_info(repo_root: Path | None = None) -> dict[str, Any]:
    """Payload for GET /api/rivalatch/knock-link. Never carries a key."""
    tip = local_git_tip(repo_root)
    sha = tip.get("sha")
    link = build_deep_link(sha) if sha else None
    return {
        "ok": bool(link),
        "sha": sha,
        "ref": tip.get("ref"),
        "repo": REPO_URI,
        "deep_link": link,
        "door": DOOR_DEFAULT,
        "note": (
            "Lodges the local checkout tip on Rivalatch (smoke GET / on docs/). "
            "Only commits pushed to GitHub can be cloned. No key on this page."
            if link
            else "HOLD: local git tip unknown (not a git checkout). No link built."
        ),
    }


# ---------------------------------------------------------------------------
# Lodge (CI ship receipt)
# ---------------------------------------------------------------------------


def _request(
    method: str,
    url: str,
    api_key: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = 120.0,
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-Api-Key", api_key)
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "qoresence-rivalatch-knock/1")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        parsed = {"raw": raw[:300]}
    return status, parsed if isinstance(parsed, dict) else {"value": parsed}


def lodge(
    sha: str,
    *,
    api_key: str,
    door: str = DOOR_DEFAULT,
    surface: str = "ship",
    poll_s: float = 2.0,
    max_polls: int = 60,
) -> dict[str, Any]:
    door = door.rstrip("/")
    body = build_gate_body(sha, idempotency_key=idempotency_key_for(sha, surface=surface))
    code, run = _request("POST", f"{door}/v1/gate/run", api_key, body=body)
    door_word = {202: "Lodged", 200: "Recalled", 409: "Occupied/Contested"}.get(code, "Error")
    out: dict[str, Any] = {
        "sha": sha.lower(),
        "idempotency_key": body["idempotency_key"],
        "run_http": code,
        "door": door_word,
        "job_id": run.get("job_id"),
        "verdict": None,
        "fail_class": None,
    }
    job_id = run.get("job_id")
    if code not in (200, 202) or not job_id:
        out["error"] = str(run.get("detail") or run)[:300]
        return out
    for _ in range(max_polls):
        rcode, res = _request("GET", f"{door}/v1/gate/results/{job_id}", api_key)
        if rcode == 200:
            out["verdict"] = res.get("verdict")
            out["fail_class"] = res.get("fail_class")
            out["checks"] = [
                {k: c.get(k) for k in ("kind", "status", "detail")}
                for c in res.get("checks") or []
                if isinstance(c, dict)
            ]
            return out
        if rcode != 202:
            out["error"] = f"results HTTP {rcode}"
            return out
        time.sleep(poll_s)
    out["error"] = "timed out waiting for terminal result"
    return out


def _say(msg: str, *, err: bool = False) -> None:
    (sys.stderr if err else sys.stdout).write(msg + "\n")


def _cmd_lodge(args: argparse.Namespace) -> int:
    api_key = (os.environ.get(ENV_KEY) or "").strip()
    if not api_key:
        _say(f"skip-closed: {ENV_KEY} not set; nothing lodged")
        return 0
    sha = (args.sha or local_git_tip().get("sha") or "").strip().lower()
    if not is_full_sha(sha):
        _say("fail-closed: no full 40-hex sha to lodge", err=True)
        return 2
    door = (args.door or os.environ.get(ENV_DOOR) or DOOR_DEFAULT).strip()
    result = lodge(sha, api_key=api_key, door=door)
    _say(f"rivalatch door={result['door']} http={result['run_http']}")
    _say(f"job_id={result.get('job_id')}")
    _say(f"verdict={result.get('verdict')} fail_class={result.get('fail_class')}")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0 if result.get("verdict") == "pass" else 1


def _cmd_link(args: argparse.Namespace) -> int:
    sha = args.sha or local_git_tip().get("sha")
    if not sha:
        _say("HOLD: local git tip unknown", err=True)
        return 2
    _say(build_deep_link(sha))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("lodge", help="lodge type=git at sha (needs VIBEGATE_API_KEY)")
    lp.add_argument("--sha", default=None)
    lp.add_argument("--door", default=None)
    lp.add_argument("--json-out", default=None)
    lp.set_defaults(func=_cmd_lodge)
    kp = sub.add_parser("link", help="print rivalatch://knock deep-link (no key)")
    kp.add_argument("--sha", default=None)
    kp.set_defaults(func=_cmd_link)
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
