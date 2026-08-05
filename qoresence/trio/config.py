"""
TrioRetina Configuration for Qoresence
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class TrioRetinaConfig:
    """
    Configuration for trio-retina w3bstream validation.
    
    All fields are optional — validation is disabled by default.
    Enable with `enabled=True` and provide WASM path.
    """
    
    # Master enable flag
    enabled: bool = False
    
    # WASM applet path (copied from vapi-pebble-prototype/w3bstream/applet/target/...)
    wasm_path: str = "w3bstream_applet.wasm"
    
    # wasmtime runtime (CLI or Python package)
    wasmtime_path: str = "wasmtime"
    use_python_wasmtime: bool = False  # If True, use wasmtime Python bindings
    
    # Validation triggers
    validate_on_ingest: bool = False      # Validate each event at ingestion (strict)
    validate_on_flush: bool = True        # Validate batched events periodically
    flush_interval_s: float = 30.0        # Batch flush interval
    max_batch_size: int = 100             # Max events per validation batch
    
    # IoTeX RPC for block_number
    block_rpc_url: str = "https://babel-api.testnet.iotex.io"
    block_rpc_timeout_s: float = 5.0
    
    # Commitment sources (mock for now, real when ZK artifacts ready)
    pq_commitment_source: str = "mock"        # "mock" | "real"
    retina_state_commitment_source: str = "visual_oracle"  # "visual_oracle" | "mock"
    events_root_source: str = "merkle"        # "merkle" | "mock"
    
    # Node/session spine (DEPIN-1 LEG 2)
    node_session_verify: bool = False         # Opt-in gate
    node_id_prefix: str = "QORTROLLER-NODE-v0"
    
    # Events root verification
    retina_events_root_verify: bool = False   # Verify events root
    
    # Logging
    log_validation_results: bool = True
    log_failures_only: bool = False
    
    # Paths resolved at runtime
    _resolved_wasm_path: Optional[Path] = field(default=None, init=False, repr=False)
    _cached_block_number: Optional[int] = field(default=None, init=False, repr=False)
    _block_cache_ts: float = field(default=0.0, init=False, repr=False)
    
    def resolve_wasm_path(self, base_dir: Optional[Path] = None) -> Path:
        """Resolve WASM path relative to base_dir or cwd."""
        if self._resolved_wasm_path:
            return self._resolved_wasm_path
        
        path = Path(self.wasm_path)
        if not path.is_absolute() and base_dir:
            path = base_dir / path
        
        if path.exists():
            self._resolved_wasm_path = path
            return path
        
        # Try common locations
        for candidate in [
            Path.cwd() / self.wasm_path,
            Path.cwd() / "w3bstream" / "applet" / "target" / "wasm32-unknown-unknown" / "release" / self.wasm_path,
            Path(__file__).parent.parent.parent / "w3bstream" / "applet" / "target" / "wasm32-unknown-unknown" / "release" / self.wasm_path,
        ]:
            if candidate.exists():
                self._resolved_wasm_path = candidate
                return candidate
        
        # Return original (will fail at runtime with clear error)
        self._resolved_wasm_path = path
        return path
    
    async def get_block_number(self) -> int:
        """Get latest block number from IoTeX RPC (cached for block_rpc_timeout_s)."""
        import time
        import aiohttp
        
        now = time.time()
        if self._cached_block_number and (now - self._block_cache_ts) < self.block_rpc_timeout_s:
            return self._cached_block_number
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.block_rpc_url,
                    json={"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
                    timeout=aiohttp.ClientTimeout(total=self.block_rpc_timeout_s)
                ) as resp:
                    data = await resp.json()
                    block_hex = data.get("result", "0x0")
                    self._cached_block_number = int(block_hex, 16)
                    self._block_cache_ts = now
                    return self._cached_block_number
        except Exception:
            # Fallback: use cached or approximate
            if self._cached_block_number:
                return self._cached_block_number
            # Approximate: IoTeX ~5s blocks
            import time
            return int(time.time() / 5)
    
    def clear_block_cache(self) -> None:
        """Clear cached block number."""
        self._cached_block_number = None
        self._block_cache_ts = 0.0


def get_default_trio_config() -> TrioRetinaConfig:
    """Get default trio-retina config (disabled)."""
    return TrioRetinaConfig()