#!/bin/bash
# =============================================================================
# Rythmiq One: Full Load Testing & Capacity Planning Pipeline
# =============================================================================
#
# This script runs the complete measurement pipeline:
# 1. Baseline CPU benchmark
# 2. Load test
# 3. Results analysis
# 4. GO/NO-GO recommendation
#
# Usage:
#   ./run_capacity_test.sh [--skip-baseline] [--skip-loadtest]
#
# Prerequisites:
#   - Python 3.11+
#   - Worker dependencies installed
#   - API server running (for load test)
#   - Test documents in test-data/fixtures/
#
# =============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_BASELINE=false
SKIP_LOADTEST=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-baseline)
            SKIP_BASELINE=true
            shift
            ;;
        --skip-loadtest)
            SKIP_LOADTEST=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Create results directory
mkdir -p "$RESULTS_DIR"

echo -e "${BLUE}=================================================================${NC}"
echo -e "${BLUE}  Rythmiq One: Capacity Planning Pipeline                        ${NC}"
echo -e "${BLUE}  Timestamp: $TIMESTAMP                                          ${NC}"
echo -e "${BLUE}=================================================================${NC}"

# =============================================================================
# Step 1: Baseline CPU Benchmark
# =============================================================================

if [ "$SKIP_BASELINE" = false ]; then
    echo -e "\n${YELLOW}[1/4] Running Baseline CPU Benchmark...${NC}"
    
    cd "$PROJECT_ROOT"
    
    # Check for test documents
    if [ ! -d "test-data/fixtures" ] || [ -z "$(ls -A test-data/fixtures 2>/dev/null)" ]; then
        echo -e "${YELLOW}Warning: No test documents found in test-data/fixtures/${NC}"
        echo "Creating synthetic test documents..."
        mkdir -p test-data/fixtures
        
        # Create simple test images using Python
        python3 - <<'EOF'
import os
from PIL import Image
import random

output_dir = "test-data/fixtures"
os.makedirs(output_dir, exist_ok=True)

# Create 20 test images with varying characteristics
for i in range(20):
    # Random size between 600x800 and 1200x1600
    width = random.randint(600, 1200)
    height = random.randint(800, 1600)
    
    # Create image with some noise/pattern
    img = Image.new('RGB', (width, height), color=(255, 255, 255))
    
    # Add some random pixels to simulate document content
    pixels = img.load()
    for _ in range(width * height // 10):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        gray = random.randint(0, 100)
        pixels[x, y] = (gray, gray, gray)
    
    # Save with varying quality
    quality = random.choice([70, 80, 90, 95])
    img.save(f"{output_dir}/test_doc_{i:03d}.jpg", "JPEG", quality=quality)

print(f"Created 20 test documents in {output_dir}/")
EOF
    fi
    
    # Run benchmark
    python3 "$SCRIPT_DIR/benchmark.py" \
        --input "test-data/fixtures" \
        --count 50 \
        --output "$RESULTS_DIR/baseline_${TIMESTAMP}.json" \
        --verbose
    
    BASELINE_EXIT=$?
    
    if [ $BASELINE_EXIT -eq 0 ]; then
        echo -e "${GREEN}✓ Baseline benchmark complete - WITHIN BUDGET${NC}"
    elif [ $BASELINE_EXIT -eq 1 ]; then
        echo -e "${YELLOW}⚠ Baseline benchmark complete - MARGINAL${NC}"
    else
        echo -e "${RED}✗ Baseline benchmark complete - OVER BUDGET${NC}"
    fi
else
    echo -e "\n${YELLOW}[1/4] Skipping Baseline Benchmark (--skip-baseline)${NC}"
fi

# =============================================================================
# Step 2: Load Test
# =============================================================================

if [ "$SKIP_LOADTEST" = false ]; then
    echo -e "\n${YELLOW}[2/4] Running Load Test...${NC}"
    
    # Check if API is running
    API_URL="${RYTHMIQ_API_URL:-http://localhost:8000}"
    
    if ! curl -s "$API_URL/health" > /dev/null 2>&1; then
        echo -e "${YELLOW}Warning: API not reachable at $API_URL${NC}"
        echo "Start the API server before running load tests."
        echo "Skipping load test phase..."
    else
        cd "$SCRIPT_DIR"
        
        # Install locust if needed
        if ! command -v locust &> /dev/null; then
            echo "Installing locust..."
            pip install locust
        fi
        
        # Run load test (headless, 5 minutes)
        locust -f locustfile.py \
            --host "$API_URL" \
            --headless \
            -u 50 \
            -r 10 \
            -t 300s \
            --csv="$RESULTS_DIR/loadtest_${TIMESTAMP}" \
            --html="$RESULTS_DIR/loadtest_${TIMESTAMP}.html"
        
        echo -e "${GREEN}✓ Load test complete${NC}"
        echo "  Results: $RESULTS_DIR/loadtest_${TIMESTAMP}.html"
    fi
else
    echo -e "\n${YELLOW}[2/4] Skipping Load Test (--skip-loadtest)${NC}"
fi

# =============================================================================
# Step 3: Results Analysis
# =============================================================================

echo -e "\n${YELLOW}[3/4] Analyzing Results...${NC}"

# Find latest baseline results
LATEST_BASELINE=$(ls -t "$RESULTS_DIR"/baseline_*.json 2>/dev/null | head -1)

if [ -n "$LATEST_BASELINE" ]; then
    echo "Analyzing: $LATEST_BASELINE"
    
    # Extract key metrics using Python
    python3 - "$LATEST_BASELINE" <<'EOF'
import json
import sys

with open(sys.argv[1]) as f:
    data = json.load(f)

summary = data.get("summary", {})

print("\n" + "=" * 60)
print("CAPACITY ANALYSIS SUMMARY")
print("=" * 60)

avg_cpu = summary.get("avg_cpu_seconds", 0)
monthly_1000 = summary.get("projected_monthly_cpu_hours_1000", 0)
status = summary.get("budget_status_1000", "UNKNOWN")

print(f"\nAverage CPU per document: {avg_cpu:.3f} seconds")
print(f"Projected @ 1000 docs/day: {monthly_1000:.1f} CPU-hours/month")
print(f"Budget (200 hrs) Status: {status}")

# Calculate max sustainable
if avg_cpu > 0:
    max_volume = int((200 * 3600) / (avg_cpu * 30))
    print(f"Maximum sustainable volume: {max_volume} docs/day")

# Stage breakdown
stages = summary.get("stage_breakdown", {})
if stages:
    print("\nStage Breakdown (avg CPU seconds):")
    total_stage = sum(stages.values())
    for stage, cpu in sorted(stages.items(), key=lambda x: -x[1]):
        pct = (cpu / total_stage * 100) if total_stage > 0 else 0
        bar = "█" * int(pct / 3)
        print(f"  {stage:20s} {cpu:6.3f}s ({pct:5.1f}%) {bar}")

print("\n" + "=" * 60)
EOF
else
    echo "No baseline results found."
fi

# =============================================================================
# Step 4: GO/NO-GO Assessment
# =============================================================================

echo -e "\n${YELLOW}[4/4] GO/NO-GO Assessment...${NC}"

if [ -n "$LATEST_BASELINE" ]; then
    # Check budget status
    BUDGET_STATUS=$(python3 -c "
import json
with open('$LATEST_BASELINE') as f:
    data = json.load(f)
print(data.get('summary', {}).get('budget_status_1000', 'UNKNOWN'))
")
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    case $BUDGET_STATUS in
        "UNDER")
            echo -e "  ${GREEN}████████████████████████████████████████████████████████████${NC}"
            echo -e "  ${GREEN}█                                                          █${NC}"
            echo -e "  ${GREEN}█                    ✅ GO                                 █${NC}"
            echo -e "  ${GREEN}█                                                          █${NC}"
            echo -e "  ${GREEN}█   System can support 1,000 docs/day within budget        █${NC}"
            echo -e "  ${GREEN}█                                                          █${NC}"
            echo -e "  ${GREEN}████████████████████████████████████████████████████████████${NC}"
            ;;
        "MARGINAL")
            echo -e "  ${YELLOW}████████████████████████████████████████████████████████████${NC}"
            echo -e "  ${YELLOW}█                                                          █${NC}"
            echo -e "  ${YELLOW}█                    ⚠️  MARGINAL GO                       █${NC}"
            echo -e "  ${YELLOW}█                                                          █${NC}"
            echo -e "  ${YELLOW}█   Close to budget limit - monitor closely                █${NC}"
            echo -e "  ${YELLOW}█   Consider optimization if traffic increases             █${NC}"
            echo -e "  ${YELLOW}█                                                          █${NC}"
            echo -e "  ${YELLOW}████████████████████████████████████████████████████████████${NC}"
            ;;
        "OVER")
            echo -e "  ${RED}████████████████████████████████████████████████████████████${NC}"
            echo -e "  ${RED}█                                                          █${NC}"
            echo -e "  ${RED}█                    ❌ ADJUST REQUIRED                     █${NC}"
            echo -e "  ${RED}█                                                          █${NC}"
            echo -e "  ${RED}█   Budget exceeded - optimization or volume reduction     █${NC}"
            echo -e "  ${RED}█   required before launch                                 █${NC}"
            echo -e "  ${RED}█                                                          █${NC}"
            echo -e "  ${RED}████████████████████████████████████████████████████████████${NC}"
            ;;
        *)
            echo -e "  ${BLUE}████████████████████████████████████████████████████████████${NC}"
            echo -e "  ${BLUE}█                                                          █${NC}"
            echo -e "  ${BLUE}█                    ❓ INCONCLUSIVE                        █${NC}"
            echo -e "  ${BLUE}█                                                          █${NC}"
            echo -e "  ${BLUE}█   Could not determine budget status                      █${NC}"
            echo -e "  ${BLUE}█   Review results manually                                █${NC}"
            echo -e "  ${BLUE}█                                                          █${NC}"
            echo -e "  ${BLUE}████████████████████████████████████████████████████████████${NC}"
            ;;
    esac
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
    echo -e "${RED}Cannot assess - no measurement data available${NC}"
fi

# =============================================================================
# Summary
# =============================================================================

echo -e "\n${BLUE}=================================================================${NC}"
echo -e "${BLUE}  Pipeline Complete                                              ${NC}"
echo -e "${BLUE}=================================================================${NC}"
echo ""
echo "Results saved to: $RESULTS_DIR/"
echo ""
echo "Next steps:"
echo "  1. Review detailed results in $RESULTS_DIR/"
echo "  2. Fill out GO_NOGO_DECISION.md with measured values"
echo "  3. Get sign-off from leads"
echo ""
echo "Documentation:"
echo "  - Capacity Plan: infra/load-testing/CAPACITY_PLANNING.md"
echo "  - Decision Form: infra/load-testing/GO_NOGO_DECISION.md"
echo ""
