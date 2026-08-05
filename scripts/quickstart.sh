#!/usr/bin/env bash
# Qoresence × trio-retina Quickstart Script
# Run this as a new developer to get up and running in <5 minutes

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     Qoresence × trio-retina Quickstart                          ║"
echo "║     Gets you from zero to validated session in <5 min           ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo

# ──────────────────────────────────────────────────────────────────────
# Step 1: Check prerequisites
# ──────────────────────────────────────────────────────────────────────
log_info "Step 1: Checking prerequisites..."

check_cmd() {
    if command -v "$1" >/dev/null 2>&1; then
        log_success "$1 found: $($1 --version 2>&1 | head -1)"
    else
        log_error "$1 not found. Please install it."
        return 1
    fi
}

MISSING=0
check_cmd python3 || MISSING=1
check_cmd pip || MISSING=1
check_cmd git || MISSING=1

# Optional but recommended
if command -v docker >/dev/null 2>&1; then
    log_success "docker found: $(docker --version)"
else
    log_warn "docker not found (optional - needed for real WASM validation)"
fi

if command -v wasmtime >/dev/null 2>&1; then
    log_success "wasmtime found: $(wasmtime --version)"
else
    log_warn "wasmtime not found (optional - needed for real WASM validation)"
fi

if [[ $MISSING -eq 1 ]]; then
    log_error "Missing required tools. Please install them and re-run."
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# Step 2: Python environment
# ──────────────────────────────────────────────────────────────────────
log_info "Step 2: Setting up Python environment..."

if [[ ! -d ".venv" ]]; then
    log_info "Creating virtual environment..."
    python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

log_info "Upgrading pip..."
pip install --upgrade pip >/dev/null 2>&1

log_info "Installing Qoresence with trio extras..."
pip install -e ".[trio]" >/dev/null 2>&1

log_success "Python environment ready"

# ──────────────────────────────────────────────────────────────────────
# Step 3: Verify WASM applet
# ──────────────────────────────────────────────────────────────────────
log_info "Step 3: Checking WASM applet..."

WASM_PATH="$REPO_ROOT/w3bstream_applet.wasm"
if [[ -f "$WASM_PATH" ]]; then
    SIZE=$(stat -c%s "$WASM_PATH" 2>/dev/null || stat -f%z "$WASM_PATH" 2>/dev/null)
    log_success "WASM applet found: $(numfmt --to=iec "$SIZE" 2>/dev/null || echo "${SIZE} bytes")"
else
    log_warn "WASM applet not found at $WASM_PATH"
    log_info "For real validation, copy from vapi-pebble-prototype:"
    log_info "  cp ../vapi-pebble-prototype/w3bstream/applet/target/wasm32-unknown-unknown/release/w3bstream_applet.wasm ."
    log_info "Continuing with mock validation..."
fi

# ──────────────────────────────────────────────────────────────────────
# Step 4: Run tests
# ──────────────────────────────────────────────────────────────────────
log_info "Step 4: Running test suite..."

if python -m pytest tests/ -q --tb=short 2>&1 | tail -5; then
    log_success "All tests passed"
else
    log_error "Tests failed. Check output above."
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────
# Step 5: Dry-run with trio-retina
# ──────────────────────────────────────────────────────────────────────
log_info "Step 5: Running trio-retina dry-run..."

DRY_RUN_CMD=(
    python -m qoresence.cli --dry-run --trio
    --trio-wasm-path="$WASM_PATH"
    --trio-validate-on-flush
    --trio-flush-interval=30
)

if [[ -f "$WASM_PATH" ]]; then
    "${DRY_RUN_CMD[@]}" 2>&1 | tail -5
else
    # Without WASM, use mock
    "${DRY_RUN_CMD[@]}" 2>&1 | tail -5
fi

log_success "Dry-run complete"

# ──────────────────────────────────────────────────────────────────────
# Step 6: Show next steps
# ──────────────────────────────────────────────────────────────────────
echo
echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║     Quickstart Complete! 🎉                                      ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo
echo "Next steps:"
echo
echo "  1. Run a live session with trio-retina validation:"
echo "     qoresence --trio --streamer --controller --outcome --screen --visual"
echo
echo "  2. Or run with Docker (for real WASM + ZKSepProof):"
echo "     docker build -t qoresence:latest ."
echo "     docker run --rm qoresence:latest --dry-run --trio \\"
echo "       --trio-wasm-path=/app/w3bstream_applet.wasm --trio-validate-on-flush"
echo
echo "  3. Read the runbook for production deployment:"
echo "     cat docs/trio-retina-runbook.md"
echo
echo "  4. View benchmarks:"
echo "     cat benchmark_results.json"
echo
echo "  5. Key docs:"
echo "     docs/trio-retina-integration.md    - Architecture"
echo "     docs/trio-retina-runbook.md        - Operations"
echo "     qoresence/trio/                    - Module source"
echo
echo "Environment variables for production:"
echo "  export QORESENCE_TRIO_ENABLED=1"
echo "  export QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm"
echo "  export QORESENCE_TRIO_VALIDATE_ON_FLUSH=1"
echo "  export QORESENCE_TRIO_PQ_COMMITMENT_SOURCE=real  # needs ZKSepProof artifacts"
echo
echo "Happy validating! 🚀"