@echo off
REM Qoresence x trio-retina Quickstart Script (Windows)
REM Run this as a new developer to get up and running in <5 minutes

setlocal enabledelayedexpansion

echo ╔══════════════════════════════════════════════════════════════════╗
echo ║     Qoresence x trio-retina Quickstart                          ║
echo ║     Gets you from zero to validated session in <5 min           ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.

REM ──────────────────────────────────────────────────────────────────────
REM Step 1: Check prerequisites
REM ──────────────────────────────────────────────────────────────────────
echo [INFO] Step 1: Checking prerequisites...

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] python not found. Please install Python 3.11+ from python.org
    exit /b 1
) else (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do echo [OK] python found: %%i
)

where pip >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip not found. Please ensure pip is installed with Python.
    exit /b 1
) else (
    echo [OK] pip found
)

where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] git not found. Please install Git from git-scm.com
    exit /b 1
) else (
    echo [OK] git found
)

where docker >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] docker not found (optional - needed for real WASM validation)
) else (
    for /f "tokens=*" %%i in ('docker --version 2^>^&1') do echo [OK] docker found: %%i
)

where wasmtime >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] wasmtime not found (optional - needed for real WASM validation)
) else (
    for /f "tokens=*" %%i in ('wasmtime --version 2^>^&1') do echo [OK] wasmtime found: %%i
)

echo.

REM ──────────────────────────────────────────────────────────────────────
REM Step 2: Python environment
REM ──────────────────────────────────────────────────────────────────────
echo [INFO] Step 2: Setting up Python environment...

if not exist .venv (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [INFO] Upgrading pip...
python -m pip install --upgrade pip >nul 2>&1

echo [INFO] Installing Qoresence with trio extras...
pip install -e ".[trio]" >nul 2>&1

echo [OK] Python environment ready
echo.

REM ──────────────────────────────────────────────────────────────────────
REM Step 3: Verify WASM applet
REM ──────────────────────────────────────────────────────────────────────
echo [INFO] Step 3: Checking WASM applet...

set WASM_PATH=w3bstream_applet.wasm
if exist %WASM_PATH% (
    for %%A in (%WASM_PATH%) do echo [OK] WASM applet found: %%~zA bytes
) else (
    echo [WARN] WASM applet not found at %WASM_PATH%
    echo [INFO] For real validation, copy from vapi-pebble-prototype:
    echo [INFO]   copy ..\vapi-pebble-prototype\w3bstream\applet\target\wasm32-unknown-unknown\release\w3bstream_applet.wasm .
    echo [INFO] Continuing with mock validation...
)
echo.

REM ──────────────────────────────────────────────────────────────────────
REM Step 4: Run tests
REM ──────────────────────────────────────────────────────────────────────
echo [INFO] Step 4: Running test suite...

python -m pytest tests/ -q --tb=short 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Tests failed. Check output above.
    exit /b 1
) else (
    echo [OK] All tests passed
)
echo.

REM ──────────────────────────────────────────────────────────────────────
REM Step 5: Dry-run with trio-retina
REM ──────────────────────────────────────────────────────────────────────
echo [INFO] Step 5: Running trio-retina dry-run...

if exist %WASM_PATH% (
    python -m qoresence.cli --dry-run --trio --trio-wasm-path=%WASM_PATH% --trio-validate-on-flush --trio-flush-interval=30 2>&1
) else (
    python -m qoresence.cli --dry-run --trio --trio-wasm-path=%WASM_PATH% --trio-validate-on-flush --trio-flush-interval=30 2>&1
)

echo [OK] Dry-run complete
echo.

REM ──────────────────────────────────────────────────────────────────────
REM Step 6: Show next steps
REM ──────────────────────────────────────────────────────────────────────
echo ╔══════════════════════════════════════════════════════════════════╗
echo ║     Quickstart Complete!                                         ║
echo ╚══════════════════════════════════════════════════════════════════╝
echo.
echo Next steps:
echo.
echo   1. Run a live session with trio-retina validation:
echo      qoresence --trio --streamer --controller --outcome --screen --visual
echo.
echo   2. Or run with Docker (for real WASM + ZKSepProof):
echo      docker build -t qoresence:latest .
echo      docker run --rm qoresence:latest --dry-run --trio ^
echo        --trio-wasm-path=/app/w3bstream_applet.wasm --trio-validate-on-flush
echo.
echo   3. Read the runbook for production deployment:
echo      type docs\trio-retina-runbook.md
echo.
echo   4. View benchmarks:
echo      type benchmark_results.json
echo.
echo   5. Key docs:
echo      docs\trio-retina-integration.md    - Architecture
echo      docs\trio-retina-runbook.md        - Operations
echo      qoresence\trio\                    - Module source
echo.
echo Environment variables for production:
echo   set QORESENCE_TRIO_ENABLED=1
echo   set QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm
echo   set QORESENCE_TRIO_VALIDATE_ON_FLUSH=1
echo   set QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=real  ^(needs ZKSepProof artifacts^)
echo.
echo Happy validating!