"""
Wasmtime Runner for trio-retina w3bstream Applet

Executes the WASM applet's `handle_poac_payload` function via wasmtime CLI
or Python wasmtime bindings.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from .config import TrioRetinaConfig
from .payload import EvmLogPayload

log = logging.getLogger(__name__)


@dataclass
class WasmResult:
    """Result of WASM applet execution."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    payload: EvmLogPayload | None = None

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    @property
    def error_description(self) -> str:
        """Human-readable description of exit code."""
        descriptions = {
            0: "OK",
            1: "Bad pointer / null input",
            2: "UTF-8 decode error",
            3: "JSON parse error",
            4: "Block cadence invalid (not multiple of 64)",
            5: "PQ proof resolution failed",
            6: "Retina state commitment invalid",
            7: "Events root invalid",
            8: "Node/session gate failed",
        }
        return descriptions.get(self.exit_code, f"Unknown exit code {self.exit_code}")


class WasmtimeRunner:
    """
    Runs the w3bstream applet WASM via wasmtime.

    Supports two modes:
    1. CLI subprocess (default) — calls `wasmtime run --invoke handle_poac_payload ...`
    2. Python wasmtime bindings — uses `wasmtime` package directly
    """

    def __init__(self, config: TrioRetinaConfig):
        self.config = config
        self._wasm_path: Path | None = None

    def _get_wasm_path(self) -> Path:
        """Get resolved WASM path."""
        if self._wasm_path:
            return self._wasm_path
        self._wasm_path = self.config.resolve_wasm_path()
        return self._wasm_path

    def _build_cli_args(self, payload_json: str) -> list[str]:
        """Build wasmtime CLI arguments."""
        wasm_path = self._get_wasm_path()

        # Write payload to stdin, invoke handle_poac_payload
        # wasmtime run --invoke handle_poac_payload <wasm> -- <input>
        # Actually, wasmtime CLI for custom entrypoint:
        # wasmtime run --invoke handle_poac_payload <wasm> <input_bytes>
        # But handle_poac_payload takes (ptr, size) — need to pass via stdin

        # The applet expects raw bytes on stdin, returns exit code
        # We'll use: echo -n '<json>' | wasmtime run --invoke handle_poac_payload <wasm>

        return [
            self.config.wasmtime_path,
            "run",
            "--invoke",
            "handle_poac_payload",
            str(wasm_path),
        ]

    async def run(self, payload: EvmLogPayload) -> WasmResult:
        """Run WASM applet with given payload."""
        if self.config.use_python_wasmtime:
            return await self._run_python(payload)
        return await self._run_cli(payload)

    async def _run_cli(self, payload: EvmLogPayload) -> WasmResult:
        """Run via wasmtime CLI subprocess."""
        wasm_path = self._get_wasm_path()

        if not wasm_path.exists():
            return WasmResult(
                exit_code=-1,
                stdout="",
                stderr=f"WASM file not found: {wasm_path}",
                duration_ms=0,
                payload=payload,
            )

        payload_json = payload.to_json()
        payload_bytes = payload_json.encode("utf-8")

        cmd = [
            self.config.wasmtime_path,
            "run",
            "--invoke",
            "handle_poac_payload",
            str(wasm_path),
        ]

        log.debug(f"Running wasmtime: {' '.join(cmd)}")
        log.debug(f"Payload: {payload_json}")

        start = time.perf_counter()

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate(input=payload_bytes)
            duration_ms = (time.perf_counter() - start) * 1000

            result = WasmResult(
                exit_code=proc.returncode,
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
                duration_ms=duration_ms,
                payload=payload,
            )

            if self.config.log_validation_results:
                if result.ok or not self.config.log_failures_only:
                    log.info(
                        f"trio-retina validation: exit={result.exit_code} ({result.error_description}) in {duration_ms:.1f}ms"
                    )
                else:
                    log.warning(
                        f"trio-retina validation FAILED: exit={result.exit_code} ({result.error_description})"
                    )

            return result

        except FileNotFoundError:
            return WasmResult(
                exit_code=-1,
                stdout="",
                stderr=f"wasmtime not found at {self.config.wasmtime_path}",
                duration_ms=0,
                payload=payload,
            )
        except Exception as e:
            return WasmResult(
                exit_code=-1,
                stdout="",
                stderr=f"Execution error: {e}",
                duration_ms=0,
                payload=payload,
            )

    async def _run_python(self, payload: EvmLogPayload) -> WasmResult:
        """Run via Python wasmtime bindings."""
        try:
            import wasmtime
        except ImportError:
            return WasmResult(
                exit_code=-1,
                stdout="",
                stderr="wasmtime Python package not installed",
                duration_ms=0,
                payload=payload,
            )

        wasm_path = self._get_wasm_path()

        if not wasm_path.exists():
            return WasmResult(
                exit_code=-1,
                stdout="",
                stderr=f"WASM file not found: {wasm_path}",
                duration_ms=0,
                payload=payload,
            )

        payload_json = payload.to_json()
        payload_bytes = payload_json.encode("utf-8")

        start = time.perf_counter()

        try:
            engine = wasmtime.Engine()
            store = wasmtime.Store(engine)
            module = wasmtime.Module.from_file(engine, str(wasm_path))
            instance = wasmtime.Instance(store, module, [])

            handle_func = instance.exports(store)["handle_poac_payload"]
            memory = instance.exports(store)["memory"]
            heap_base = instance.exports(store)["__heap_base"].value(store)

            # Place payload just above the heap base. Grow memory if needed.
            # Reserve a small guard so the applet's allocator (if any) has
            # headroom before reaching our data.
            offset = heap_base + 4096
            needed = offset + len(payload_bytes) + 1024
            if needed > memory.data_len(store):
                pages = (needed - memory.data_len(store) + 65535) // 65536
                memory.grow(store, pages)

            memory.write(store, payload_bytes, offset)

            exit_code = handle_func(store, offset, len(payload_bytes))

            duration_ms = (time.perf_counter() - start) * 1000
            return WasmResult(
                exit_code=exit_code,
                stdout="",
                stderr="",
                duration_ms=duration_ms,
                payload=payload,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return WasmResult(
                exit_code=-1,
                stdout="",
                stderr=f"Python wasmtime error: {e}",
                duration_ms=duration_ms,
                payload=payload,
            )


def create_runner(config: TrioRetinaConfig) -> WasmtimeRunner:
    """Factory function to create WasmtimeRunner."""
    return WasmtimeRunner(config)
