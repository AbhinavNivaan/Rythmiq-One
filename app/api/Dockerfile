# app/api/Dockerfile
# Rythmiq One — Cloud Run API
#
# Multi-stage build: builder installs deps into /opt/venv, runtime copies only venv + code.
# Build context: project root (.)
#
# Build:
#   docker build --platform linux/amd64 -f app/api/Dockerfile -t rythmiq/api:local .
#
# Run (with fake env for local smoke test):
#   docker run --rm -p 8080:8080 \
#     -e SUPABASE_URL=http://test -e SUPABASE_ANON_KEY=test \
#     -e SUPABASE_SERVICE_ROLE_KEY=test -e SUPABASE_JWT_SECRET=test \
#     -e DO_SPACES_ENDPOINT=https://test.com -e DO_SPACES_REGION=sgp1 \
#     -e DO_SPACES_BUCKET=test -e DO_SPACES_ACCESS_KEY=test \
#     -e DO_SPACES_SECRET_KEY=test -e WEBHOOK_SECRET=test \
#     rythmiq/api:local

# -----------------------------------------------------------------------------
# Stage 1: Base — minimal system deps
# -----------------------------------------------------------------------------
FROM --platform=linux/amd64 python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# -----------------------------------------------------------------------------
# Stage 2: Builder — install Python packages into /opt/venv
# -----------------------------------------------------------------------------
FROM base AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY app/api/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements.txt \
    && find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true \
    && find /opt/venv -type f -name "*.pyc" -delete 2>/dev/null || true

# -----------------------------------------------------------------------------
# Stage 3: Runtime — minimal production image
# -----------------------------------------------------------------------------
FROM base AS runtime

# Non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 api

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy app source (app/ includes app/__init__.py + app/api/)
COPY --chown=api:api app/ ./app/

# PYTHONPATH must point to /app so 'from app.api...' imports resolve
ENV PYTHONPATH=/app

USER api

# Verify all critical imports succeed at build time
RUN python -c "\
import sys; print(f'Python: {sys.version}'); \
import fastapi; print(f'fastapi: {fastapi.__version__}'); \
import uvicorn; print(f'uvicorn: ok'); \
import boto3; print(f'boto3: {boto3.__version__}'); \
import supabase; print(f'supabase: ok'); \
import httpx; print(f'httpx: {httpx.__version__}'); \
print('All imports OK'); \
"

ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
