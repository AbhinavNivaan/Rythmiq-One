#!/usr/bin/env bash
# =============================================================================
# Camber Integration Verification Script
# =============================================================================
# Run this script to verify all components are configured correctly
# before submitting a real job.
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "Camber Production Integration Check"
echo "=============================================="
echo ""

# Load .env if exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo -e "${GREEN}✓${NC} Loaded .env file"
else
    echo -e "${RED}✗${NC} No .env file found"
    echo "  → Copy .env.camber to .env and fill in values"
    exit 1
fi

echo ""
echo "1. Checking environment variables..."
echo "----------------------------------------------"

check_var() {
    local var_name=$1
    local var_value="${!var_name}"
    if [ -z "$var_value" ]; then
        echo -e "  ${RED}✗${NC} $var_name is NOT SET"
        return 1
    elif [[ "$var_value" == *"REPLACE"* ]]; then
        echo -e "  ${YELLOW}!${NC} $var_name has placeholder value"
        return 1
    else
        # Mask sensitive values
        if [[ "$var_name" == *"KEY"* ]] || [[ "$var_name" == *"SECRET"* ]]; then
            echo -e "  ${GREEN}✓${NC} $var_name = ${var_value:0:8}..."
        else
            echo -e "  ${GREEN}✓${NC} $var_name = $var_value"
        fi
        return 0
    fi
}

CHECKS_PASSED=true

check_var "EXECUTION_BACKEND" || CHECKS_PASSED=false
check_var "CAMBER_API_URL" || CHECKS_PASSED=false
check_var "CAMBER_API_KEY" || CHECKS_PASSED=false
check_var "CAMBER_APP_NAME" || CHECKS_PASSED=false
check_var "WEBHOOK_SECRET" || CHECKS_PASSED=false
check_var "SUPABASE_URL" || CHECKS_PASSED=false
check_var "DO_SPACES_ENDPOINT" || CHECKS_PASSED=false
check_var "DO_SPACES_BUCKET" || CHECKS_PASSED=false

echo ""
echo "2. Verifying Camber API connectivity..."
echo "----------------------------------------------"

if [ -n "$CAMBER_API_KEY" ] && [[ "$CAMBER_API_KEY" != *"REPLACE"* ]]; then
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $CAMBER_API_KEY" \
        "${CAMBER_API_URL}/v1/apps" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" == "200" ]; then
        echo -e "  ${GREEN}✓${NC} Camber API accessible (HTTP $HTTP_CODE)"
    elif [ "$HTTP_CODE" == "401" ]; then
        echo -e "  ${RED}✗${NC} Camber API returned 401 Unauthorized"
        echo "    → Check CAMBER_API_KEY is valid"
        CHECKS_PASSED=false
    elif [ "$HTTP_CODE" == "000" ]; then
        echo -e "  ${RED}✗${NC} Could not connect to Camber API"
        echo "    → Check CAMBER_API_URL and network connectivity"
        CHECKS_PASSED=false
    else
        echo -e "  ${YELLOW}!${NC} Camber API returned HTTP $HTTP_CODE"
    fi
else
    echo -e "  ${YELLOW}!${NC} Skipping API check (no valid API key)"
fi

echo ""
echo "3. Checking Docker image..."
echo "----------------------------------------------"

IMAGE_TAG="rythmiq-worker-cpu:v1"
if docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Local image exists: $IMAGE_TAG"
else
    echo -e "  ${YELLOW}!${NC} Local image not found: $IMAGE_TAG"
    echo "    → Build with: docker build -f worker/Dockerfile.cpu -t $IMAGE_TAG ./worker"
fi

echo ""
echo "4. Checking camber-app.json..."
echo "----------------------------------------------"

if [ -f "camber-app.json" ]; then
    echo -e "  ${GREEN}✓${NC} camber-app.json exists"
    
    # Check required fields
    if grep -q '"engineType": "container"' camber-app.json; then
        echo -e "  ${GREEN}✓${NC} engineType is 'container'"
    else
        echo -e "  ${YELLOW}!${NC} engineType should be 'container' for Docker execution"
    fi
    
    if grep -q '"image":' camber-app.json; then
        IMAGE_REF=$(grep '"image":' camber-app.json | sed 's/.*"image": "\([^"]*\)".*/\1/')
        echo -e "  ${GREEN}✓${NC} image reference: $IMAGE_REF"
    else
        echo -e "  ${RED}✗${NC} No image reference in camber-app.json"
        CHECKS_PASSED=false
    fi
else
    echo -e "  ${RED}✗${NC} camber-app.json not found"
    CHECKS_PASSED=false
fi

echo ""
echo "5. Python environment check..."
echo "----------------------------------------------"

if python -c "from app.api.config import get_settings; s = get_settings(); print(f'Backend: {s.execution_backend}')" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} Config loads successfully"
else
    echo -e "  ${RED}✗${NC} Failed to load Python config"
    echo "    → Check Python environment and dependencies"
    CHECKS_PASSED=false
fi

echo ""
echo "=============================================="
if [ "$CHECKS_PASSED" = true ]; then
    echo -e "${GREEN}All checks passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Push Docker image to registry:"
    echo "   docker tag rythmiq-worker-cpu:v1 registry.digitalocean.com/rythmiq-registry/worker-cpu:v1"
    echo "   docker push registry.digitalocean.com/rythmiq-registry/worker-cpu:v1"
    echo ""
    echo "2. Deploy Camber app:"
    echo "   camber app create --file camber-app.json"
    echo ""
    echo "3. Start API with ngrok (for testing):"
    echo "   uvicorn app.api.main:app --host 0.0.0.0 --port 8000 &"
    echo "   ngrok http 8000"
    echo ""
    echo "4. Set WEBHOOK_BASE_URL to ngrok URL in .env"
    echo ""
    echo "5. Submit a test job!"
else
    echo -e "${RED}Some checks failed. Please fix the issues above.${NC}"
    exit 1
fi
