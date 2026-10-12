"""Append-only JSONL writer + offline verifier for the truth feed hash chain."""

from __future__ import annotations

import json
import logging
import threading
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from qoresence.truth.model import (
    GENESIS_HASH,
    LABEL_VERIFIED,
    LEVEL_SCREEN_INPUT,
    SCHEMA,
    SCORE_KINDS,
    TruthFact,
    body_bytes,
    fact_hash,
)
from qoresence.truth.signing import SIG_ALG, Signer, key_id_for, verify_signature

log = logging.getLogger(__name__)


def last_record(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 65536))
            tail = fh.read().decode("utf-8", errors="replace").strip().splitlines()
    except OSError:
        return None
    for line in reversed(tail):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("schema") == SCHEMA:
            return rec
    return None


class TruthChainWriter:
    """Hash-chains and (optionally) signs facts, appends them to one JSONL file.

    Never emits bus events. The private lock only guards seq/prev_hash and the
    file handle; nothing is called back while it is held.
    """

    def __init__(
        self,
        path: Path,
        *,
        signer: Signer | None = None,
        recent: int = 512,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.signer = signer
        self._lock = threading.Lock()
        self._recent: deque[dict[str, Any]] = deque(maxlen=max(16, int(recent)))
        self._seq = 0
        self._prev = GENESIS_HASH
        last = last_record(self.path) if self.path.exists() else None
        if last is not None:
            # Resume an existing session file: keep the chain unbroken.
            self._seq = int(last.get("seq", -1)) + 1
            self._prev = str(last.get("hash") or GENESIS_HASH)
        self._fh = self.path.open("a", encoding="utf-8")
        self.written = 0
        self.sign_failures = 0

    @property
    def signed(self) -> bool:
        return self.signer is not None

    @property
    def next_seq(self) -> int:
        return self._seq

    def append(self, fact: TruthFact) -> dict[str, Any] | None:
        """Chain + sign + write one fact. Returns the record, or None if refused."""
        with self._lock:
            fact.seq = self._seq
            fact.prev_hash = self._prev
            fact.signed = self.signer is not None
            fact.key_id = self.signer.key_id if self.signer is not None else None
            fact.hash = ""
            fact.signature = None
            rec = fact.to_record()
            rec["hash"] = fact_hash(rec)
            rec["signature"] = None
            if self.signer is not None:
                try:
                    rec["signature"] = {
                        "alg": SIG_ALG,
                        "key_id": self.signer.key_id,
                        "sig": self.signer.sign(body_bytes(rec)),
                    }
                except Exception as e:
                    # Fail-closed: never write a fact that claims signed=true unsigned.
                    self.sign_failures += 1
                    log.warning("truth feed: sign failed (%s); fact dropped", type(e).__name__)
                    return None
            line = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            self._fh.write(line + "\n")
            self._fh.flush()
            self._seq += 1
            self._prev = rec["hash"]
            self._recent.append(rec)
            self.written += 1
            return rec

    def recent(self, since: int | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._recent)
        if since is not None:
            items = [r for r in items if int(r.get("seq", -1)) > int(since)]
        return items[-max(1, int(limit)) :]

    def close(self) -> None:
        with self._lock:
            try:
                self._fh.close()
            except Exception:
                pass


# ──────────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────────


def _err(errors: list[dict[str, Any]], line: int, seq: Any, msg: str) -> None:
    if len(errors) < 50:
        errors.append({"line": line, "seq": seq, "error": msg})


def verify_records(
    records: Iterable[dict[str, Any] | str], *, pubkey_hex: str | None = None
) -> dict[str, Any]:
    """Verify chain integrity, structure (honesty rules) and signatures.

    ``pubkey_hex`` pins the expected key. Without it the key published in the
    first ``session_start`` fact is used (trust on first use; reported as
    ``pubkey_source: "session_start"``).
    """
    errors: list[dict[str, Any]] = []
    prev = GENESIS_HASH
    expect_seq: int | None = None
    signed_mode: bool | None = None
    key_id: str | None = None
    pub = pubkey_hex.lower() if pubkey_hex else None
    pub_source = "pinned" if pub else None
    sig_checked = 0
    count = 0
    last_kind = None
    crypto_missing = False

    for i, raw in enumerate(records, start=1):
        if isinstance(raw, str):
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                _err(errors, i, None, "invalid_json")
                break
        else:
            rec = raw
        if not isinstance(rec, dict):
            _err(errors, i, None, "not_an_object")
            break
        count += 1
        seq = rec.get("seq")
        if rec.get("schema") != SCHEMA:
            _err(errors, i, seq, "unknown_schema")
        if expect_seq is None:
            expect_seq = seq if isinstance(seq, int) else 0
            if expect_seq != 0 and rec.get("prev_hash") == GENESIS_HASH:
                _err(errors, i, seq, "genesis_seq_not_zero")
            prev = rec.get("prev_hash") if expect_seq != 0 else GENESIS_HASH
        if seq != expect_seq:
            _err(errors, i, seq, f"seq_gap expected {expect_seq}")
        expect_seq = (seq if isinstance(seq, int) else expect_seq) + 1
        if rec.get("prev_hash") != prev:
            _err(errors, i, seq, "prev_hash_mismatch")
        h = fact_hash(rec)
        if rec.get("hash") != h:
            _err(errors, i, seq, "hash_mismatch")
        prev = rec.get("hash") or h

        # Structural honesty: digits only on score facts, labels consistent.
        kind = rec.get("kind")
        last_kind = kind
        ver = rec.get("verification") if isinstance(rec.get("verification"), dict) else {}
        if kind in SCORE_KINDS:
            sc = rec.get("scores")
            if (
                not isinstance(sc, dict)
                or not isinstance(sc.get("home"), int)
                or not isinstance(sc.get("away"), int)
            ):
                _err(errors, i, seq, "score_fact_without_scores")
            if not (rec.get("source") or {}).get("ticket_id"):
                _err(errors, i, seq, "score_fact_without_ticket")
        elif rec.get("scores") is not None:
            _err(errors, i, seq, "scores_on_non_score_fact")
        if ver.get("label") == LABEL_VERIFIED and ver.get("level") != LEVEL_SCREEN_INPUT:
            _err(errors, i, seq, "verified_label_without_input")
        if kind == "session_start" and pub is None:
            meta_pub = (rec.get("meta") or {}).get("pubkey")
            if meta_pub:
                pub = str(meta_pub).lower()
                pub_source = "session_start"

        # Signatures
        signed = bool(rec.get("signed"))
        if signed_mode is None:
            signed_mode = signed
            key_id = rec.get("key_id")
        elif signed != signed_mode:
            _err(errors, i, seq, "mixed_signed_unsigned")
        sig = rec.get("signature")
        if not signed:
            if sig is not None or rec.get("key_id"):
                _err(errors, i, seq, "unsigned_fact_carries_signature")
            continue
        if rec.get("key_id") != key_id:
            _err(errors, i, seq, "key_id_changed")
        if not isinstance(sig, dict) or sig.get("alg") != "ed25519" or not sig.get("sig"):
            _err(errors, i, seq, "missing_signature")
            continue
        if sig.get("key_id") != rec.get("key_id"):
            _err(errors, i, seq, "signature_key_id_mismatch")
        if pub is None:
            _err(errors, i, seq, "no_public_key")
            continue
        if key_id_for(bytes.fromhex(pub)) != rec.get("key_id"):
            _err(errors, i, seq, "public_key_does_not_match_key_id")
            continue
        try:
            good = verify_signature(pub, str(sig.get("sig")), body_bytes(rec))
        except RuntimeError:
            crypto_missing = True
            continue
        if good:
            sig_checked += 1
        else:
            _err(errors, i, seq, "bad_signature")

    if crypto_missing:
        errors.append({"line": None, "seq": None, "error": "cryptography_missing"})
    return {
        "ok": not errors and count > 0,
        "count": count,
        "signed": bool(signed_mode),
        "signatures_checked": sig_checked,
        "key_id": key_id,
        "pubkey": pub,
        "pubkey_source": pub_source,
        "head_hash": prev if count else None,
        "complete": last_kind == "session_end",
        "errors": errors,
    }


def verify_file(path: str | Path, *, pubkey_hex: str | None = None) -> dict[str, Any]:
    p = Path(path)
    with p.open("r", encoding="utf-8") as fh:
        out = verify_records(fh, pubkey_hex=pubkey_hex)
    out["path"] = str(p)
    return out
