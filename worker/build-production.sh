#!/bin/bash
# =============================================================================
# Rythmiq Worker - Production Image Build Script
# =============================================================================
# 
# Builds the pre-baked worker image with ALL dependencies and models.
# MUST use buildx for linux/amd64 target (required for Camber).
#
# Usage:
#   ./build-production.sh                    # Build and load locally
#   ./build-production.sh --push             # Build and push to registry
#   ./build-production.sh --tag v1.2.3       # Build with specific tag
#
# Requirements:
#   - Docker with buildx support
#   - ~10 minutes build time (first build)
#   - ~5GB disk space during build
#
# =============================================================================

set -euo pipefail

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${REGISTRY:-docker.io}"
IMAGE_NAME="${IMAGE_NAME:-rythmiq/worker}"
TAG="${TAG:-production}"
PLATFORM="linux/amd64"
DOCKERFILE="${SCRIPT_DIR}/Dockerfile.production"

# Parse arguments
PUSH=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH=true
            shift
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------
echo "=== Pre-flight checks ==="

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: docker not found"
    exit 1
fi

# Check buildx
if ! docker buildx version &> /dev/null; then
    echo "ERROR: docker buildx not available"
    echo "Install with: docker buildx install"
    exit 1
fi

# Check Dockerfile exists
if [[ ! -f "${DOCKERFILE}" ]]; then
    echo "ERROR: Dockerfile not found: ${DOCKERFILE}"
    exit 1
fi

echo "Docker: $(docker --version)"
echo "Buildx: $(docker buildx version | head -1)"
echo "Platform: ${PLATFORM}"
echo "Image: ${FULL_IMAGE}"
echo ""

# -----------------------------------------------------------------------------
# Setup buildx builder
# -----------------------------------------------------------------------------
echo "=== Setting up buildx builder ==="

BUILDER_NAME="rythmiq-builder"

# Create builder if it doesn't exist
if ! docker buildx inspect "${BUILDER_NAME}" &> /dev/null; then
    echo "Creating buildx builder: ${BUILDER_NAME}"
    docker buildx create \
        --name "${BUILDER_NAME}" \
        --driver docker-container \
        --platform linux/amd64,linux/arm64 \
        --bootstrap
else
    echo "Using existing builder: ${BUILDER_NAME}"
fi

docker buildx use "${BUILDER_NAME}"

# -----------------------------------------------------------------------------
# Build image
# -----------------------------------------------------------------------------
echo ""
echo "=== Building production image ==="
echo "Target platform: ${PLATFORM}"
echo "This will take ~10 minutes on first build..."
echo ""

BUILD_START=$(date +%s)

BUILD_ARGS=(
    --platform "${PLATFORM}"
    --file "${DOCKERFILE}"
    --tag "${FULL_IMAGE}"
    --progress plain
)

if [[ "${PUSH}" == "true" ]]; then
    BUILD_ARGS+=(--push)
    echo "Mode: Build and PUSH to ${REGISTRY}"
else
    BUILD_ARGS+=(--load)
    echo "Mode: Build and LOAD locally"
fi

docker buildx build "${BUILD_ARGS[@]}" "${SCRIPT_DIR}"

BUILD_END=$(date +%s)
BUILD_DURATION=$((BUILD_END - BUILD_START))

echo ""
echo "=== Build complete ==="
echo "Duration: ${BUILD_DURATION} seconds"
echo "Image: ${FULL_IMAGE}"

# -----------------------------------------------------------------------------
# Post-build verification (local only)
# -----------------------------------------------------------------------------
if [[ "${PUSH}" != "true" ]]; then
    echo ""
    echo "=== Verifying image ==="
    
    # Check image size
    IMAGE_SIZE=$(docker image inspect "${FULL_IMAGE}" --format='{{.Size}}' | awk '{printf "%.0f", $1/1024/1024}')
    echo "Image size: ${IMAGE_SIZE} MB"
    
    if [[ ${IMAGE_SIZE} -gt 2048 ]]; then
        echo "WARNING: Image exceeds 2GB target (${IMAGE_SIZE} MB)"
    else
        echo "✓ Image size within 2GB target"
    fi
    
    # Quick smoke test
    echo ""
    echo "Running smoke test..."
    SMOKE_OUTPUT=$(docker run --rm --platform "${PLATFORM}" "${FULL_IMAGE}" python -c "\
import sys; \
from paddleocr import PaddleOCR; \
ocr = PaddleOCR(use_angle_cls=True, lang='en'); \
print('SMOKE_TEST_PASSED'); \
" 2>&1)
    
    if echo "${SMOKE_OUTPUT}" | grep -q "SMOKE_TEST_PASSED"; then
        echo "✓ Smoke test passed"
    else
        echo "✗ Smoke test FAILED"
        echo "${SMOKE_OUTPUT}"
        exit 1
    fi
    
    echo ""
    echo "=== Ready for deployment ==="
    echo ""
    echo "To push to registry:"
    echo "  docker push ${FULL_IMAGE}"
    echo ""
    echo "To test locally:"
    echo "  echo '{\"test\": true}' | docker run -i --rm ${FULL_IMAGE}"
fi
