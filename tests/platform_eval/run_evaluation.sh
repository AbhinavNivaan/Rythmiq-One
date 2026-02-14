#!/bin/bash
# =============================================================================
# Camber Platform Evaluation - Quick Start
# =============================================================================
# This script runs the platform evaluation tests to determine if Camber
# meets Rythmiq's latency requirements.
#
# Processing Stack Under Test:
#   ├─ PaddleOCR (OCR) - 44s init overhead
#   ├─ Google Vision API (OCR for critical docs)
#   ├─ OpenCV (auto-crop, enhancement)
#   ├─ PyMuPDF (PDF processing)
#   ├─ img2pdf (format conversion)
#   ├─ rembg (background removal) - ML model
#   └─ Pillow (DPI, compression)
#
# Prerequisites:
#   - CAMBER_API_KEY environment variable set
#   - camber CLI installed
#   - Python 3.9+
#
# Usage:
#   ./run_evaluation.sh [test_name]
#
# Tests:
#   components          - All component init baselines
#   fast_path           - Pillow + img2pdf (schema compliance)
#   enhancement         - OpenCV (auto-crop, denoise)
#   background_removal  - rembg (ML model, ~170MB)
#   pdf_processing      - PyMuPDF
#   ocr_paddle          - PaddleOCR (44s init)
#   concurrent_single   - 5 parallel jobs (single user)
#   concurrent_multi    - 9 parallel jobs (3 users)
#   all                 - Run everything
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  Camber Platform Evaluation"
echo "=============================================="
echo ""

# Check prerequisites
if [ -z "$CAMBER_API_KEY" ]; then
    echo -e "${RED}Error: CAMBER_API_KEY not set${NC}"
    echo "Run: export CAMBER_API_KEY=your_api_key"
    exit 1
fi

if ! command -v camber &> /dev/null; then
    echo -e "${RED}Error: camber CLI not found${NC}"
    echo "Install with: pip install camber"
    exit 1
fi

echo -e "${GREEN}✓${NC} CAMBER_API_KEY is set"
echo -e "${GREEN}✓${NC} camber CLI available"
echo ""

# Default test
TEST_NAME="${1:-all}"

echo "Running test: $TEST_NAME"
echo ""

# Create results directory
RESULTS_DIR="$PROJECT_ROOT/test_results"
mkdir -p "$RESULTS_DIR"

# Run the test
cd "$PROJECT_ROOT"
python3 -m tests.platform_eval.test_runner --test "$TEST_NAME"

echo ""
echo "=============================================="
echo "  Evaluation Complete"
echo "=============================================="
echo ""
echo "Results saved to: $RESULTS_DIR/"
echo ""
echo "Next steps:"
echo "  1. Review results in test_results/*.json"
echo "  2. Compare against targets in docs/CAMBER_PLATFORM_EVALUATION.md"
echo "  3. Make go/no-go decision"
