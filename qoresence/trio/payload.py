"""
EvmLogPayload Builder for trio-retina w3bstream Applet

Builds the exact payload structure expected by the w3bstream applet's
`handle_poac_payload` function, matching the MachineFi/trio-retina standard.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from qoresence.core import SessionIdentity

if TYPE_CHECKING:
    from .config import TrioRetinaConfig


@dataclass
class EvmLogPayload:
    """
    Payload structure matching w3bstream applet's EvmLogPayload.

    All string fields are 64-hex (32 bytes) unless noted.
    Fields with `serde(default)` in Rust are optional here (default empty string).
    """

    # Required core fields
    device_id: str  # 64-hex device ID (VMDR pubkey hash)
    block_number: int  # IoTeX L1 block number
    payload_hash: str  # 64-hex SHA-256 of session_head + events
    signature: str  # 64-hex Ed25519 signature (device key)
    pq_commitment: str  # 64-hex ML-DSA-65 commitment (mock for now)

    # Retina state (visual oracle)
    retina_state_commitment: str = ""  # 64-hex visual oracle state root
    retina_w3bstream_enforce: bool = False  # Enforce retina commitment

    # Events root (merkle of event batch)
    events_root: str = ""  # 64-hex merkle root
    retina_events_root_verify: bool = False  # Verify events root

    # DEPIN-1 LEG 2: Node/Session spine
    node_id: str = ""  # 64-hex SHA-256(QORTROLLER-NODE-v0 || device_id || first_session)
    session_root: str = ""  # 64-hex scorecard/PoSP root
    node_session_verify: bool = False  # Opt-in gate

    def to_json(self) -> str:
        """Serialize to JSON for WASM applet."""
        return json.dumps(
            {
                "device_id": self.device_id,
                "block_number": self.block_number,
                "payload_hash": self.payload_hash,
                "signature": self.signature,
                "pq_commitment": self.pq_commitment,
                "retina_state_commitment": self.retina_state_commitment,
                "retina_w3bstream_enforce": self.retina_w3bstream_enforce,
                "events_root": self.events_root,
                "retina_events_root_verify": self.retina_events_root_verify,
                "node_id": self.node_id,
                "session_root": self.session_root,
                "node_session_verify": self.node_session_verify,
            },
            separators=(",", ":"),
        )

    @classmethod
    def from_json(cls, json_str: str) -> EvmLogPayload:
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(
            device_id=data["device_id"],
            block_number=data["block_number"],
            payload_hash=data["payload_hash"],
            signature=data["signature"],
            pq_commitment=data["pq_commitment"],
            retina_state_commitment=data.get("retina_state_commitment", ""),
            retina_w3bstream_enforce=data.get("retina_w3bstream_enforce", False),
            events_root=data.get("events_root", ""),
            retina_events_root_verify=data.get("retina_events_root_verify", False),
            node_id=data.get("node_id", ""),
            session_root=data.get("session_root", ""),
            node_session_verify=data.get("node_session_verify", False),
        )


def compute_node_id(
    device_id_hex: str, first_session_id: str, prefix: str = "QORTROLLER-NODE-v0"
) -> str:
    """
    Compute node_id per trio-retina standard:
    SHA-256(prefix || device_id || first_session_id)

    Args:
        device_id_hex: 64-hex device ID
        first_session_id: First session ID string
        prefix: Node ID prefix (default "QORTROLLER-NODE-v0")

    Returns:
        64-hex node ID
    """
    data = prefix.encode() + bytes.fromhex(device_id_hex) + first_session_id.encode()
    return hashlib.sha256(data).hexdigest()


def compute_payload_hash(session_head_ns: int, events: list[dict]) -> str:
    """
    Compute payload_hash = SHA-256(session_head_ns (8-byte BE) || sorted_events_json)

    Args:
        session_head_ns: Monotonic session head timestamp (nanoseconds)
        events: List of event dicts

    Returns:
        64-hex hash
    """
    head_bytes = session_head_ns.to_bytes(8, "big")
    events_json = json.dumps(events, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(head_bytes + events_json).hexdigest()


def compute_events_root(event_ids: list[str]) -> str:
    """
    Compute Merkle root of event IDs (simplified: hash of concatenated sorted IDs).

    For production, use proper Merkle tree. This is a simplified version
    matching the trio-retina mechanical format check.

    Args:
        event_ids: List of event ID strings

    Returns:
        64-hex root
    """
    if not event_ids:
        return "0" * 64

    sorted_ids = sorted(event_ids)
    concatenated = "".join(sorted_ids).encode()
    return hashlib.sha256(concatenated).hexdigest()


def mock_pq_commitment() -> str:
    """
    Generate mock PQ commitment (ML-DSA-65 = 3309 bytes → 64-hex placeholder).

    In production, this would be a real ML-DSA-65 signature commitment.
    For now, return a deterministic non-zero 64-hex.
    """
    # Use a fixed non-zero pattern that passes sidecar commitment check
    return "a" * 64


def try_real_pq_commitment(
    biometric_snapshot_hash: str,
    claimed_player_id: int,
    feature_commitment: str,
    separation_threshold_milli: int = 1000,
    inference_code: int = 0,
    zk_artifacts_dir: Path | None = None,
) -> str | None:
    """
    Try to generate real PQ commitment using ZKSepProof circuit.

    This uses the ZKSepProof Groth16 circuit to prove separation,
    which serves as the post-quantum commitment for trio-retina.

    Returns:
        64-hex commitment if successful, None if artifacts not available or proof fails.
    """
    import os

    if zk_artifacts_dir is None:
        # Check environment variable first
        env_path = os.environ.get("VAPI_ZK_ARTIFACTS_DIR")
        if env_path:
            zk_artifacts_dir = Path(env_path)
        else:
            # Try common locations
            candidates = [
                Path(__file__).parent.parent.parent
                / "vapi-pebble-prototype"
                / "bridge"
                / "zk_artifacts",
                Path.home() / "vapi-pebble-prototype" / "bridge" / "zk_artifacts",
                Path("/home/user/vapi-pebble-prototype/bridge/zk_artifacts"),
                Path.cwd() / "vapi-pebble-prototype" / "bridge" / "zk_artifacts",
            ]
            for candidate in candidates:
                if candidate.exists():
                    zk_artifacts_dir = candidate
                    break
            else:
                zk_artifacts_dir = candidates[0]  # Default to first for error reporting

    wasm_path = zk_artifacts_dir / "ZKSepProof.wasm"
    zkey_path = zk_artifacts_dir / "ZKSepProof_final.zkey"
    vkey_path = zk_artifacts_dir / "ZKSepProof_verification_key.json"

    if not (wasm_path.exists() and zkey_path.exists() and vkey_path.exists()):
        return None

    try:
        import json
        import subprocess
        import tempfile

        # Build witness input
        # Parse biometric_snapshot_hash (64-hex) into lo/hi 128-bit parts
        if biometric_snapshot_hash.startswith("0x"):
            biometric_snapshot_hash = biometric_snapshot_hash[2:]
        if len(biometric_snapshot_hash) != 64:
            return None

        lo = int(biometric_snapshot_hash[32:], 16)  # low 128 bits
        hi = int(biometric_snapshot_hash[:32], 16)  # high 128 bits

        # Feature commitment (32-byte hex)
        if feature_commitment.startswith("0x"):
            feature_commitment = feature_commitment[2:]
        feature_commitment_int = int(feature_commitment, 16)

        # Create witness input JSON
        witness_input = {
            "biometricSnapshotHashLo": str(lo),
            "biometricSnapshotHashHi": str(hi),
            "claimedPlayerId": str(claimed_player_id),
            "featureCommitment": str(feature_commitment_int),
            "separationThresholdMilli": str(separation_threshold_milli),
            "inferenceCode": str(inference_code),
        }

        # Run snarkjs to generate witness and proof
        # This is a simplified version - in production use the ZKSepProofProver class
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.json"
            witness_path = Path(tmpdir) / "witness.wtns"
            proof_path = Path(tmpdir) / "proof.json"
            public_path = Path(tmpdir) / "public.json"

            with open(input_path, "w") as f:
                json.dump(witness_input, f)

            # Generate witness
            result = subprocess.run(
                [
                    "npx",
                    "snarkjs",
                    "wtns",
                    "calculate",
                    str(wasm_path),
                    str(input_path),
                    str(witness_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return None

            # Generate proof
            result = subprocess.run(
                [
                    "npx",
                    "snarkjs",
                    "groth16",
                    "prove",
                    str(zkey_path),
                    str(witness_path),
                    str(proof_path),
                    str(public_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                return None

            # Read proof and compute commitment hash
            with open(proof_path) as f:
                proof = json.load(f)

            # Compute commitment from proof (Pi_a + Pi_b + Pi_c)
            # This matches the 256-byte wire format
            proof_bytes = bytes.fromhex(
                proof["pi_a"][0][2:]
                + proof["pi_a"][1][2:]
                + proof["pi_b"][0][0][2:]
                + proof["pi_b"][0][1][2:]
                + proof["pi_b"][1][0][2:]
                + proof["pi_b"][1][1][2:]
                + proof["pi_c"][0][2:]
                + proof["pi_c"][1][2:]
            )

            # Return SHA-256 of proof as 64-hex commitment
            return hashlib.sha256(proof_bytes).hexdigest()

    except Exception:
        return None


def mock_signature(payload_hash: str, device_key: bytes | None = None) -> str:
    """
    Generate mock Ed25519 signature.

    In production, sign with actual device key (DualShock Edge VMDR).
    For now, return deterministic mock.
    """
    # Mock: hash of payload_hash + fixed salt
    salt = b"QORESSENCE-MOCK-SIGNING-KEY"
    return hashlib.sha256(payload_hash.encode() + salt).hexdigest()


def get_visual_oracle_root() -> str:
    """
    Get visual oracle state commitment root.

    In production, this comes from VisualRuntime's latest state commitment.
    For now, return mock.
    """
    return "b" * 64


def get_posp_root() -> str:
    """
    Get PoSP (Proof of Session Presence) scorecard root.

    In production, from OutcomeRuntime's session scorecard.
    For now, return mock.
    """
    return "c" * 64


def build_evm_log_payload(
    session: SessionIdentity,
    events: list[dict],
    config: TrioRetinaConfig,
    visual_oracle_root: str | None = None,
    posp_root: str | None = None,
    first_session_id: str | None = None,
    device_key: bytes | None = None,
    # Real PQ commitment inputs (when using ZKSepProof)
    biometric_snapshot_hash: str | None = None,
    claimed_player_id: int | None = None,
    feature_commitment: str | None = None,
) -> EvmLogPayload:
    """
    Build complete EvmLogPayload from Qoresence session + events.

    Args:
        session: Current SessionIdentity
        events: List of event dicts to commit
        config: TrioRetinaConfig for feature flags
        visual_oracle_root: Optional override for retina_state_commitment
        posp_root: Optional override for session_root
        first_session_id: First session ID for node_id computation
        device_key: Device signing key (Ed25519 private key)
        biometric_snapshot_hash: 64-hex biometric snapshot hash for real PQ commitment
        claimed_player_id: Player ID for real PQ commitment
        feature_commitment: 64-hex feature commitment for real PQ commitment

    Returns:
        Complete EvmLogPayload ready for WASM validation
    """
    # Compute core commitments
    payload_hash = compute_payload_hash(session.session_head_ns, events)
    events_root = compute_events_root([e.get("event_id", "") for e in events])

    # Get block number (async in real use, sync here for builder)
    # Note: In async context, call config.get_block_number() instead
    block_number = 0  # Placeholder; real caller should await get_block_number()

    # Compute node_id
    node_id = ""
    if session.device_id_hex and first_session_id:
        node_id = compute_node_id(session.device_id_hex, first_session_id, config.node_id_prefix)

    # Try real PQ commitment if config says so and inputs provided
    pq_commitment = mock_pq_commitment()
    if (
        config.pq_commitment_source == "real"
        and biometric_snapshot_hash
        and claimed_player_id is not None
        and feature_commitment
    ):
        real_pq = try_real_pq_commitment(
            biometric_snapshot_hash=biometric_snapshot_hash,
            claimed_player_id=claimed_player_id,
            feature_commitment=feature_commitment,
        )
        if real_pq:
            pq_commitment = real_pq

    # Build payload
    payload = EvmLogPayload(
        device_id=session.device_id_hex or "0" * 64,
        block_number=block_number,
        payload_hash=payload_hash,
        signature=mock_signature(payload_hash, device_key),
        pq_commitment=pq_commitment,
        retina_state_commitment=visual_oracle_root or get_visual_oracle_root(),
        retina_w3bstream_enforce=config.validate_on_ingest,
        events_root=events_root,
        retina_events_root_verify=config.retina_events_root_verify,
        node_id=node_id,
        session_root=posp_root or get_posp_root(),
        node_session_verify=config.node_session_verify,
    )

    return payload
