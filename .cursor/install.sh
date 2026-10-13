#!/usr/bin/env bash
# Qoresence Cloud Agent install — idempotent dependency refresh.
# Runs after the repo is checked out. Safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── System libraries ────────────────────────────────────────────────────────
# opencv-python-headless / onnxruntime need libGL + glib + libgomp at runtime;
# python3-venv is required to create the project virtualenv on Ubuntu.
if command -v sudo >/dev/null 2>&1; then APT="sudo apt-get"; else APT="apt-get"; fi
$APT update -qq
$APT install -y --no-install-recommends \
  libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
  python3-venv python3.12-venv build-essential curl

# ── snarkjs (optional) ──────────────────────────────────────────────────────
# trio-retina's real ZK PQ commitment shells out to snarkjs; the test suite
# mocks WASM, but CI ships it so keep parity. Node is present in the base image.
if ! command -v snarkjs >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo env "PATH=$PATH" npm install -g snarkjs || echo "snarkjs install skipped (optional)"
  else
    npm install -g snarkjs || echo "snarkjs install skipped (optional)"
  fi
fi

# ── Python virtualenv + editable install ────────────────────────────────────
# Extras mirror CI (.[trio,test]) plus dev (ruff/mypy), deck (FastAPI/uvicorn),
# mcp, and httpx so the full test suite and the Retina Deck server both run.
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[trio,test,dev,deck,mcp]" httpx

echo "Qoresence install complete. Activate with: source .venv/bin/activate"
