#!/bin/bash
# =============================================================================
# Sync Worker Code to Camber Stash
# =============================================================================
#
# Uploads the worker Python code to Camber Stash for BASE engine jobs.
# Use this when NOT using the Docker image approach.
#
# Usage:
#   ./sync-to-stash.sh
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAMBER_USERNAME="${CAMBER_USERNAME:-abhinavprakash15151692}"
STASH_PATH="stash://${CAMBER_USERNAME}/rythmiq-worker-v3"

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
if [[ -z "${CAMBER_API_KEY:-}" ]]; then
    echo "ERROR: CAMBER_API_KEY not set"
    exit 1
fi

if ! command -v camber &> /dev/null; then
    echo "ERROR: camber CLI not found"
    exit 1
fi

# -----------------------------------------------------------------------------
# Sync files
# -----------------------------------------------------------------------------
echo "=== Syncing worker code to Camber Stash ==="
echo "Source: ${SCRIPT_DIR}"
echo "Destination: ${STASH_PATH}/"
echo ""

# Create directory
camber stash mkdir "${STASH_PATH}" --api-key "${CAMBER_API_KEY}" 2>/dev/null || true

# Upload Python files
FILES=(
    "worker.py"
    "models.py"
    "errors.py"
    "requirements-pinned.txt"
)

for file in "${FILES[@]}"; do
    if [[ -f "${SCRIPT_DIR}/${file}" ]]; then
        echo "Uploading ${file}..."
        camber stash cp "${SCRIPT_DIR}/${file}" "${STASH_PATH}/${file}" \
            --api-key "${CAMBER_API_KEY}"
    fi
done

# Upload directories
DIRS=(
    "processors"
    "storage"
    "errors"
    "schema"
)

for dir in "${DIRS[@]}"; do
    if [[ -d "${SCRIPT_DIR}/${dir}" ]]; then
        echo "Uploading ${dir}/..."
        camber stash cp -r "${SCRIPT_DIR}/${dir}" "${STASH_PATH}/${dir}" \
            --api-key "${CAMBER_API_KEY}"
    fi
done

echo ""
echo "=== Sync complete ==="
echo "Files available at: ${STASH_PATH}/"
echo ""
echo "To list contents:"
echo "  camber stash ls ${STASH_PATH}/ --api-key \"\${CAMBER_API_KEY}\""
