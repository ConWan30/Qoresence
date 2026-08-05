# Qoresence Dockerfile — Phase 9 Deployment + trio-retina
# Multi-stage build for minimal production image

# ──────────────────────────────────────────────────────────────────────────────
# BUILD STAGE
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for snarkjs (ZKSepProof real PQ commitment)
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY qoresence/ ./qoresence/
COPY tools/ ./tools/

# Install in development mode with trio extras
RUN pip install --no-cache-dir -e .[trio]

# Install wasmtime for trio-retina WASM execution
RUN curl -fsSL https://wasmtime.dev/install.sh | bash -s -- --version 16.0.0
ENV PATH="/root/.wasmtime/bin:${PATH}"

# Install snarkjs globally for ZKSepProof
RUN npm install -g snarkjs

# ──────────────────────────────────────────────────────────────────────────────
# RUNTIME STAGE
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for snarkjs
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install wasmtime
RUN curl -fsSL https://wasmtime.dev/install.sh | bash -s -- --version 16.0.0
ENV PATH="/root/.wasmtime/bin:${PATH}"

# Install snarkjs globally for ZKSepProof
RUN npm install -g snarkjs

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.wasmtime /root/.wasmtime
COPY --from=builder /usr/lib/node_modules /usr/lib/node_modules
COPY --from=builder /usr/bin/node /usr/bin/node
COPY --from=builder /usr/bin/npm /usr/bin/npm
COPY --from=builder /usr/bin/npx /usr/bin/npx

# Copy application code
COPY --from=builder /app/qoresence /app/qoresence
COPY --from=builder /app/tools /app/tools

# Copy WASM applet if available (from vapi-pebble-prototype)
COPY --from=builder /app/w3bstream_applet.wasm /app/w3bstream_applet.wasm

# Copy ZKSepProof artifacts for real PQ commitment
COPY vapi-pebble-prototype/bridge/zk_artifacts/ZKSepProof.wasm /app/zk_artifacts/ZKSepProof.wasm
COPY vapi-pebble-prototype/bridge/zk_artifacts/ZKSepProof_final.zkey /app/zk_artifacts/ZKSepProof_final.zkey
COPY vapi-pebble-prototype/bridge/zk_artifacts/ZKSepProof_verification_key.json /app/zk_artifacts/ZKSepProof_verification_key.json

# Create non-root user
RUN useradd --no-create-home --shell /bin/bash qoresence \
    && chown -R qoresence:qoresence /app

USER qoresence

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QORESENCE_LOG_LEVEL=INFO \
    QORESENCE_TRIO_WASM_PATH=/app/w3bstream_applet.wasm \
    VAPI_ZK_ARTIFACTS_DIR=/app/zk_artifacts

# Expose WebSocket port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import qoresence.cli; print('OK')" || exit 1

# Default command
ENTRYPOINT ["qoresence"]
CMD ["--help"]