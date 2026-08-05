# Qoresence Dockerfile — Phase 9 Deployment
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
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY qoresence/ ./qoresence/
COPY tools/ ./tools/

# Install in development mode
RUN pip install --no-cache-dir -e .

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
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --from=builder /app/qoresence /app/qoresence
COPY --from=builder /app/tools /app/tools

# Create non-root user
RUN useradd --no-create-home --shell /bin/bash qoresence \
    && chown -R qoresence:qoresence /app

USER qoresence

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QORESENCE_LOG_LEVEL=INFO

# Expose WebSocket port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import qoresence.cli; print('OK')" || exit 1

# Default command
ENTRYPOINT ["qoresence"]
CMD ["--help"]