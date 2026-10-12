"""Local Ed25519 signing for the truth feed (optional ``[truth]`` extra).

Key: ``~/.qoresence/truth_key`` (hex 32-byte seed, mode 0600), generated on
first use; public key exported next to it as ``truth_key.pub`` (hex). Override
the path with ``QORESENCE_TRUTH_KEY``. The private key never leaves the machine
and is never logged, served or put in a fact.

``cryptography`` is not a core dependency. Without it (or with a key that
cannot be used safely) the feed falls back to an unsigned hash chain and every
fact says ``signed: false`` — it never writes something that looks signed.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SIG_ALG = "ed25519"


def default_key_path() -> Path:
    raw = os.getenv("QORESENCE_TRUTH_KEY")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".qoresence" / "truth_key"


def crypto_available() -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: F401
            Ed25519PrivateKey,
        )
    except Exception:
        return False
    return True


def key_id_for(pub_raw: bytes) -> str:
    return hashlib.sha256(pub_raw).hexdigest()[:16]


@dataclass
class Signer:
    """Holds the private key in memory; exposes only public material."""

    _priv: object
    pubkey_hex: str
    key_id: str

    def sign(self, data: bytes) -> str:
        return self._priv.sign(data).hex()  # type: ignore[attr-defined]


def _write_new_key(path: Path) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    priv = Ed25519PrivateKey.generate()
    seed = priv.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as fh:
        fh.write(seed.hex() + "\n")
    return seed


def load_or_create_signer(path: Path | None = None) -> tuple[Signer | None, str]:
    """Return ``(signer, reason)``. ``signer`` is None when signing is unavailable.

    Reasons: ``ok``, ``cryptography_missing``, ``key_permissions_too_open``,
    ``key_unreadable``.
    """
    if not crypto_available():
        return None, "cryptography_missing"
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    p = Path(path) if path is not None else default_key_path()
    try:
        if p.exists():
            if sys.platform != "win32" and (p.stat().st_mode & 0o077):
                log.warning("truth feed: %s is group/other readable; not signing", p)
                return None, "key_permissions_too_open"
            seed = bytes.fromhex(p.read_text(encoding="ascii").strip())
        else:
            try:
                seed = _write_new_key(p)
                log.info("truth feed: generated new Ed25519 key at %s", p)
            except FileExistsError:  # raced with another process
                seed = bytes.fromhex(p.read_text(encoding="ascii").strip())
        priv = Ed25519PrivateKey.from_private_bytes(seed)
    except Exception as e:
        log.warning("truth feed: signing key unusable (%s); unsigned chain", type(e).__name__)
        return None, "key_unreadable"
    pub = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    try:
        pub_path = p.with_name(p.name + ".pub")
        if not pub_path.exists() or pub_path.read_text(encoding="ascii").strip() != pub.hex():
            pub_path.write_text(pub.hex() + "\n", encoding="ascii")
    except OSError:
        pass
    return Signer(_priv=priv, pubkey_hex=pub.hex(), key_id=key_id_for(pub)), "ok"


def verify_signature(pubkey_hex: str, sig_hex: str, data: bytes) -> bool:
    """True only for a valid Ed25519 signature. Raises RuntimeError without cryptography."""
    if not crypto_available():
        raise RuntimeError("cryptography_missing")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        pk = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        pk.verify(bytes.fromhex(sig_hex), data)
    except (InvalidSignature, ValueError):
        return False
    return True
