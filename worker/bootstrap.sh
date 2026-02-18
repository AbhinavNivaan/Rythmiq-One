#!/bin/bash
# =============================================================================
# Camber Worker Bootstrap Script
# =============================================================================
#
# This script sets up the environment before running the worker.
# It configures:
# - PYTHONPATH to use cached dependencies from Stash (if available)
# - OCR backend selection (Tesseract by default, PaddleOCR optional)
# - Environment variables for optimal performance
#
# Usage:
#   ./bootstrap.sh python3 worker.py
#   echo '{"job_id": "..."}' | ./bootstrap.sh python3 worker.py
#
# Environment variables:
#   OCR_BACKEND=tesseract (default) or paddleocr
#
# =============================================================================

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -----------------------------------------------------------------------------
# OCR Backend Selection (default: tesseract for fast init)
# -----------------------------------------------------------------------------
export OCR_BACKEND="${OCR_BACKEND:-tesseract}"
echo "[bootstrap] OCR backend: $OCR_BACKEND" >&2

# -----------------------------------------------------------------------------
# Configure cached dependencies (if available)
# -----------------------------------------------------------------------------
CACHED_DEPS="${SCRIPT_DIR}/cached_deps"

if [[ -d "$CACHED_DEPS" ]]; then
    echo "[bootstrap] Using cached dependencies from: $CACHED_DEPS" >&2
    export PYTHONPATH="${CACHED_DEPS}:${PYTHONPATH:-}"
fi

# -----------------------------------------------------------------------------
# PaddleOCR setup (only if using paddleocr backend)
# -----------------------------------------------------------------------------
if [[ "$OCR_BACKEND" == "paddleocr" ]]; then
    CACHED_MODELS="${SCRIPT_DIR}/paddlex_models"
    if [[ -d "$CACHED_MODELS" ]]; then
        echo "[bootstrap] Using cached PaddleOCR models from: $CACHED_MODELS" >&2
        ln -sf "$CACHED_MODELS" "${HOME}/.paddlex" 2>/dev/null || true
    fi
    export PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
    export FLAGS_use_mkldnn=0
fi

# -----------------------------------------------------------------------------
# Performance tuning
# -----------------------------------------------------------------------------
# Limit OpenMP threads to avoid contention on small nodes
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-2}

# -----------------------------------------------------------------------------
# Execute the actual command
# -----------------------------------------------------------------------------
exec "$@"
