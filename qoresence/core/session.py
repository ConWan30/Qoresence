"""
Qoresence Session Authority — Phase 2

Single source of truth for session identity.
Mints: session_id, session_head_ns, device_id_hex
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import os
import time
import uuid


@dataclass(frozen=True)
class SessionIdentity:
    """Immutable session identity triplet."""
    session_id: str
    session_head_ns: int
    device_id_hex: str

    def __post_init__(self):
        if not self.session_id:
            raise ValueError("session_id cannot be empty")
        if self.session_head_ns <= 0:
            raise ValueError("session_head_ns must be positive")
        if self.device_id_hex and len(self.device_id_hex) != 64:
            raise ValueError("device_id_hex must be 64 hex chars (32 bytes)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_head_ns": self.session_head_ns,
            "device_id_hex": self.device_id_hex,
        }


class SessionAuthority:
    """
    Authority for minting and managing session identities.

    Single source of truth — all lobes get identity from here.
    """

    _current_session: Optional[SessionIdentity] = None

    @classmethod
    def mint(
        cls,
        session_id: Optional[str] = None,
        device_id_hex: Optional[str] = None,
        session_head_ns: Optional[int] = None,
    ) -> SessionIdentity:
        """
        Mint a new session identity.

        Args:
            session_id: Optional custom session ID. If not provided, generates one.
            device_id_hex: Optional 64-char device ID. If not provided, reads from env or leaves empty.
            session_head_ns: Optional monotonic timestamp. If not provided, uses time.monotonic_ns().

        Returns:
            SessionIdentity with all three fields populated.
        """
        now_ns = session_head_ns or time.monotonic_ns()

        # Generate session_id if not provided
        if session_id is None or not session_id.strip():
            session_id = f"qoresence_{uuid.uuid4().hex[:12]}"

        # Resolve device_id_hex
        if device_id_hex is None:
            device_id_hex = os.environ.get("QORESENCE_DEVICE_ID_HEX", "")

        identity = SessionIdentity(
            session_id=session_id,
            session_head_ns=now_ns,
            device_id_hex=device_id_hex or "",
        )

        cls._current_session = identity
        return identity

    @classmethod
    def current(cls) -> Optional[SessionIdentity]:
        """Get the current active session identity."""
        return cls._current_session

    @classmethod
    def clear(cls) -> None:
        """Clear the current session."""
        cls._current_session = None

    @classmethod
    def from_env(cls) -> SessionIdentity:
        """
        Create session identity from environment variables.

        Expected env vars:
        - QORESENCE_SESSION_ID
        - QORESENCE_DEVICE_ID_HEX
        - QORESENCE_SESSION_HEAD_NS (optional)
        """
        session_id = os.environ.get("QORESENCE_SESSION_ID")
        device_id_hex = os.environ.get("QORESENCE_DEVICE_ID_HEX")
        session_head_ns_str = os.environ.get("QORESENCE_SESSION_HEAD_NS")

        session_head_ns = int(session_head_ns_str) if session_head_ns_str else None

        return cls.mint(
            session_id=session_id,
            device_id_hex=device_id_hex,
            session_head_ns=session_head_ns,
        )


# Need to import Any for type hint
from typing import Any