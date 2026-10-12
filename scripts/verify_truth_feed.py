#!/usr/bin/env python3
"""Offline verifier for a Qoresence truth feed JSONL file (qoresence.truth.fact.v0).

Standalone: stdlib only, plus ``cryptography`` for Ed25519 signatures. Does not
import the qoresence package, so it runs on any machine with the file.

    python scripts/verify_truth_feed.py logs/truth/truth_<session>.jsonl
    python scripts/verify_truth_feed.py feed.jsonl --pubkey <hex>   # pin the key
    python scripts/verify_truth_feed.py feed.jsonl --json

Checks: every line's sha256 over the canonical body (sort_keys, compact, ASCII,
minus ``hash``/``signature``), seq contiguity, prev_hash links, signed/unsigned
consistency, Ed25519 signatures, and the honesty rules (digits only on score
facts that cite a ConfirmTicket; ``verified`` only with ``screen+input``).
Exit code 0 = ok, 1 = failed, 2 = usage / unreadable.

Limits: without a pinned --pubkey the key comes from the file's own
session_start fact (trust on first use). A cut-off tail cannot be detected
from the file alone; ``complete`` reports whether it ends with session_end.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "qoresence.truth.fact.v0"
GENESIS = "0" * 64
SCORE_KINDS = ("score_lock", "score_change")


def canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def body(rec: dict) -> bytes:
    return canonical({k: v for k, v in rec.items() if k not in ("hash", "signature")})


def ed25519_ok(pub_hex: str, sig_hex: str, data: bytes) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
            bytes.fromhex(sig_hex), data
        )
    except (InvalidSignature, ValueError):
        return False
    return True


def verify(lines: list[str], pubkey: str | None = None) -> dict:
    errors: list[dict] = []
    prev = GENESIS
    signed_mode = None
    key_id = None
    pub = pubkey.lower() if pubkey else None
    pub_source = "pinned" if pub else None
    checked = 0
    count = 0
    last_kind = None
    have_crypto = True
    try:
        import cryptography  # noqa: F401
    except ImportError:
        have_crypto = False

    def err(n: int, seq: object, msg: str) -> None:
        errors.append({"line": n, "seq": seq, "error": msg})

    for n, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except ValueError:
            err(n, None, "invalid_json")
            break
        count += 1
        seq = rec.get("seq")
        if rec.get("schema") != SCHEMA:
            err(n, seq, "unknown_schema")
        if seq != count - 1:
            err(n, seq, f"seq_gap expected {count - 1}")
        if rec.get("prev_hash") != prev:
            err(n, seq, "prev_hash_mismatch")
        h = hashlib.sha256(body(rec)).hexdigest()
        if rec.get("hash") != h:
            err(n, seq, "hash_mismatch")
        prev = rec.get("hash") or h
        kind = last_kind = rec.get("kind")
        ver = rec.get("verification") or {}
        if kind in SCORE_KINDS:
            sc = rec.get("scores") or {}
            if not isinstance(sc.get("home"), int) or not isinstance(sc.get("away"), int):
                err(n, seq, "score_fact_without_scores")
            if not (rec.get("source") or {}).get("ticket_id"):
                err(n, seq, "score_fact_without_ticket")
        elif rec.get("scores") is not None:
            err(n, seq, "scores_on_non_score_fact")
        if ver.get("label") == "verified" and ver.get("level") != "screen+input":
            err(n, seq, "verified_label_without_input")
        if kind == "session_start" and pub is None and (rec.get("meta") or {}).get("pubkey"):
            pub = str(rec["meta"]["pubkey"]).lower()
            pub_source = "session_start"
        signed = bool(rec.get("signed"))
        if signed_mode is None:
            signed_mode, key_id = signed, rec.get("key_id")
        elif signed != signed_mode:
            err(n, seq, "mixed_signed_unsigned")
        sig = rec.get("signature")
        if not signed:
            if sig is not None or rec.get("key_id"):
                err(n, seq, "unsigned_fact_carries_signature")
            continue
        if rec.get("key_id") != key_id:
            err(n, seq, "key_id_changed")
        if not isinstance(sig, dict) or sig.get("alg") != "ed25519" or not sig.get("sig"):
            err(n, seq, "missing_signature")
            continue
        if pub is None:
            err(n, seq, "no_public_key")
            continue
        if hashlib.sha256(bytes.fromhex(pub)).hexdigest()[:16] != rec.get("key_id"):
            err(n, seq, "public_key_does_not_match_key_id")
            continue
        if not have_crypto:
            continue
        if ed25519_ok(pub, str(sig["sig"]), body(rec)):
            checked += 1
        else:
            err(n, seq, "bad_signature")
    if signed_mode and not have_crypto:
        errors.append({"line": None, "seq": None, "error": "cryptography_missing"})
    return {
        "ok": not errors and count > 0,
        "count": count,
        "signed": bool(signed_mode),
        "signatures_checked": checked,
        "key_id": key_id,
        "pubkey": pub,
        "pubkey_source": pub_source,
        "head_hash": prev if count else None,
        "complete": last_kind == "session_end",
        "errors": errors[:50],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", help="truth feed JSONL file")
    ap.add_argument("--pubkey", help="expected Ed25519 public key (hex); pins the signer")
    ap.add_argument("--json", action="store_true", help="print the full JSON result")
    a = ap.parse_args(argv)
    try:
        lines = Path(a.path).read_text(encoding="utf-8").splitlines()
    except OSError as e:
        print(f"cannot read {a.path}: {e}", file=sys.stderr)
        return 2
    res = verify(lines, a.pubkey)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        state = "OK" if res["ok"] else "FAILED"
        sig = (
            f"signed key_id={res['key_id']} ({res['signatures_checked']} sigs, "
            f"key from {res['pubkey_source']})"
            if res["signed"]
            else "UNSIGNED hash chain"
        )
        print(f"{state}: {res['count']} facts, {sig}, complete={res['complete']}")
        for e in res["errors"]:
            print(f"  line {e['line']} seq {e['seq']}: {e['error']}")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
