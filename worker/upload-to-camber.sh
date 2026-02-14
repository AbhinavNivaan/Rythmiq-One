#!/bin/bash
# =============================================================================
# Upload Production Image to Camber Stash
# =============================================================================
#
# Exports the Docker image as a tarball and uploads to Camber Stash.
# Camber can then load this image for container-based jobs.
#
# Usage:
#   ./upload-to-camber.sh
#
# Requirements:
#   - CAMBER_API_KEY environment variable
#   - camber CLI installed
#   - Production image built locally
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
IMAGE_NAME="${IMAGE_NAME:-rythmiq/worker:production}"
CAMBER_USERNAME="${CAMBER_USERNAME:-abhinavprakash15151692}"
STASH_PATH="stash://${CAMBER_USERNAME}/rythmiq-worker-v3"
TARBALL_NAME="worker-production.tar.gz"
TEMP_DIR=$(mktemp -d)

cleanup() {
    rm -rf "${TEMP_DIR}"
}
trap cleanup EXIT

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
echo "=== Pre-flight checks ==="

if [[ -z "${CAMBER_API_KEY:-}" ]]; then
    echo "ERROR: CAMBER_API_KEY not set"
    echo "Export your Camber API key: export CAMBER_API_KEY='your-key'"
    exit 1
fi

if ! command -v camber &> /dev/null; then
    echo "ERROR: camber CLI not found"
    echo "Install with: brew tap camber-ops/tap && brew install camber"
    exit 1
fi

if ! docker image inspect "${IMAGE_NAME}" &> /dev/null; then
    echo "ERROR: Image not found: ${IMAGE_NAME}"
    echo "Build first with: ./build-production.sh"
    exit 1
fi

# Verify Camber auth
echo "Verifying Camber authentication..."
camber me --api-key "${CAMBER_API_KEY}" || {
    echo "ERROR: Camber authentication failed"
    exit 1
}

echo "✓ All checks passed"
echo ""

# -----------------------------------------------------------------------------
# Export Docker image
# -----------------------------------------------------------------------------
echo "=== Exporting Docker image ==="
echo "Image: ${IMAGE_NAME}"
echo "Output: ${TEMP_DIR}/${TARBALL_NAME}"

docker save "${IMAGE_NAME}" | gzip > "${TEMP_DIR}/${TARBALL_NAME}"

TARBALL_SIZE=$(ls -lh "${TEMP_DIR}/${TARBALL_NAME}" | awk '{print $5}')
echo "Tarball size: ${TARBALL_SIZE}"
echo ""

# -----------------------------------------------------------------------------
# Upload to Camber Stash
# -----------------------------------------------------------------------------
echo "=== Uploading to Camber Stash ==="
echo "Destination: ${STASH_PATH}/"

# Create directory if needed
camber stash mkdir "${STASH_PATH}" --api-key "${CAMBER_API_KEY}" 2>/dev/null || true

# Upload tarball
echo "Uploading ${TARBALL_NAME}..."
camber stash cp "${TEMP_DIR}/${TARBALL_NAME}" "${STASH_PATH}/${TARBALL_NAME}" \
    --api-key "${CAMBER_API_KEY}"

echo ""
echo "=== Upload complete ==="
echo "Image available at: ${STASH_PATH}/${TARBALL_NAME}"
echo ""
echo "To use in Camber job:"
echo "  Load image from stash and run container"
