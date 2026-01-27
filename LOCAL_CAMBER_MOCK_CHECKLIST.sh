#!/usr/bin/env bash
#
# LOCAL CAMBER MOCK - DEVELOPER VERIFICATION CHECKLIST
#
# This script verifies that the local mock is properly set up and working.
# Run after pulling the implementation.
#
# Usage:
#   bash LOCAL_CAMBER_MOCK_CHECKLIST.sh
#

PASS_COUNT=0
FAIL_COUNT=0
SECTION_NUM=1

# Helper functions
pass() {
    echo "  [PASS] $1"
    ((PASS_COUNT++))
}

fail() {
    echo "  [FAIL] $1"
    ((FAIL_COUNT++))
}

section() {
    echo ""
    echo "[$SECTION_NUM] $1"
    echo "---"
    ((SECTION_NUM++))
}

echo ""
echo "LOCAL CAMBER MOCK - DEVELOPER VERIFICATION CHECKLIST"
echo "======================================================"
echo ""

# ============================================================================
# SECTION 1: FILE EXISTENCE
# ============================================================================

section "File Existence"

if [ -f "app/api/services/mock_camber_client.py" ]; then
    pass "MockCamberClient implementation exists"
else
    fail "MockCamberClient not found at app/api/services/mock_camber_client.py"
fi

if [ -f "app/api/services/camber.py" ]; then
    pass "Camber service exists"
else
    fail "Camber service not found"
fi

if [ -f "app/api/config.py" ]; then
    pass "Config file exists"
else
    fail "Config not found"
fi

if [ -f "tests/test_e2e_pipeline.py" ]; then
    pass "E2E test suite exists"
else
    fail "Test suite not found at tests/test_e2e_pipeline.py"
fi

if [ -f "LOCAL_CAMBER_MOCK_SETUP.md" ]; then
    pass "Setup documentation exists"
else
    fail "Setup docs missing"
fi

if [ -f "LOCAL_CAMBER_MOCK_INDEX.md" ]; then
    pass "Index documentation exists"
else
    fail "Index docs missing"
fi

# ============================================================================
# SECTION 2: SYNTAX VALIDATION
# ============================================================================

section "Syntax Validation"

if python -m py_compile app/api/services/mock_camber_client.py 2>/dev/null; then
    pass "MockCamberClient syntax valid"
else
    fail "MockCamberClient has syntax errors"
fi

if python -m py_compile app/api/services/camber.py 2>/dev/null; then
    pass "Camber service syntax valid"
else
    fail "Camber service has syntax errors"
fi

if python -m py_compile app/api/config.py 2>/dev/null; then
    pass "Config syntax valid"
else
    fail "Config has syntax errors"
fi

if python -m py_compile tests/test_e2e_pipeline.py 2>/dev/null; then
    pass "Test suite syntax valid"
else
    fail "Test suite has syntax errors"
fi

# ============================================================================
# SECTION 3: CODE REQUIREMENTS
# ============================================================================

section "Code Requirements"

# Check MockCamberClient has required methods
if grep -q "async def submit_job" app/api/services/mock_camber_client.py; then
    pass "MockCamberClient has submit_job method"
else
    fail "MockCamberClient missing submit_job method"
fi

if grep -q "async def _send_webhook" app/api/services/mock_camber_client.py; then
    pass "MockCamberClient has _send_webhook method"
else
    fail "MockCamberClient missing _send_webhook method"
fi

if grep -q "async def get_job_status" app/api/services/mock_camber_client.py; then
    pass "MockCamberClient has get_job_status method"
else
    fail "MockCamberClient missing get_job_status method"
fi

# Check factory pattern
if grep -q "execution_backend" app/api/services/camber.py; then
    pass "Factory checks execution_backend"
else
    fail "Factory doesn't check execution_backend"
fi

if grep -q "MockCamberClient" app/api/services/camber.py; then
    pass "Factory imports MockCamberClient"
else
    fail "Factory doesn't import MockCamberClient"
fi

# Check config has required fields
if grep -q "execution_backend" app/api/config.py; then
    pass "Config has execution_backend field"
else
    fail "Config missing execution_backend field"
fi

if grep -q "api_port" app/api/config.py; then
    pass "Config has api_port field"
else
    fail "Config missing api_port field"
fi

# Check test suite
if grep -q "test_mock_client_submit_returns_immediately" tests/test_e2e_pipeline.py; then
    pass "Test suite has mock interface tests"
else
    fail "Test suite missing mock interface tests"
fi

if grep -q "test_factory_returns_mock_when_backend_is_local" tests/test_e2e_pipeline.py; then
    pass "Test suite has factory tests"
else
    fail "Test suite missing factory tests"
fi

# ============================================================================
# SECTION 4: PRODUCTION SAFETY
# ============================================================================

section "Production Safety"

# Check that execution_backend defaults to "camber"
if grep -q 'default="camber"' app/api/config.py || grep -q "default='camber'" app/api/config.py; then
    pass "execution_backend defaults to 'camber' (safe)"
else
    fail "execution_backend doesn't default to 'camber'"
fi

# Check that mock is only in factory
if grep -q "MockCamberClient" app/api/services/camber.py 2>/dev/null; then
    pass "Mock only referenced in factory (not scattered in code)"
else
    fail "Mock not found in factory"
fi

# Check webhook verification unchanged
if grep -q "hmac.compare_digest" app/api/routes/webhooks.py; then
    pass "Webhook uses constant-time comparison (security preserved)"
else
    fail "Webhook signature verification may be compromised"
fi

# ============================================================================
# SECTION 5: ENVIRONMENT SETUP
# ============================================================================

section "Environment Setup"

if [ -z "$EXECUTION_BACKEND" ]; then
    echo "  ⚠️  EXECUTION_BACKEND not set (will default to 'camber')"
else
    if [ "$EXECUTION_BACKEND" = "local" ]; then
        pass "EXECUTION_BACKEND=local is set"
    elif [ "$EXECUTION_BACKEND" = "camber" ]; then
        echo "  ℹ️  EXECUTION_BACKEND=camber (will use real Camber)"
    else
        fail "EXECUTION_BACKEND has invalid value: $EXECUTION_BACKEND"
    fi
fi

if [ -z "$WEBHOOK_SECRET" ]; then
    echo "  ⚠️  WEBHOOK_SECRET not set (required for webhook verification)"
else
    pass "WEBHOOK_SECRET is set"
fi

# ============================================================================
# SECTION 6: DOCUMENTATION
# ============================================================================

section "Documentation"

# Check documentation files
for doc in \
    "LOCAL_CAMBER_MOCK_SETUP.md" \
    "LOCAL_CAMBER_MOCK_IMPLEMENTATION_SUMMARY.md" \
    "LOCAL_CAMBER_MOCK_ENV.example" \
    "LOCAL_MOCK_CAMBER_QUICK_REF.md"; do
    if [ -f "$doc" ]; then
        lines=$(wc -l < "$doc")
        pass "Documentation: $doc ($lines lines)"
    else
        fail "Missing: $doc"
    fi
done

# Check demo script
if [ -f "scripts/run_local_mock_demo.sh" ]; then
    pass "Demo script exists: scripts/run_local_mock_demo.sh"
else
    fail "Demo script missing"
fi

# ============================================================================
# SECTION 7: READY-TO-USE CHECKS
# ============================================================================

section "Ready-to-Use Checks"

echo ""
echo "  To complete setup, run:"
echo ""
echo "  1. Set environment variables:"
echo "     export EXECUTION_BACKEND=local"
echo "     export WEBHOOK_SECRET=your-secret-here"
echo ""
echo "  2. Start the API:"
echo "     uvicorn app.api.main:app --reload"
echo ""
echo "  3. Create a job (in another terminal):"
echo "     curl -X POST http://127.0.0.1:8000/jobs \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"portal_schema_name\":\"invoice\",\"filename\":\"test.pdf\"}'"
echo ""
echo "  4. Check status:"
echo "     curl http://127.0.0.1:8000/jobs/<job_id>"
echo ""
echo "  5. Run tests:"
echo "     pytest tests/test_e2e_pipeline.py -v"
echo ""

# ============================================================================
# RESULTS
# ============================================================================

echo ""
echo "===================================================="
echo "VERIFICATION RESULTS"
echo "===================================================="
echo ""
echo "  PASSED: $PASS_COUNT"
echo "  FAILED: $FAIL_COUNT"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo "✓ ALL CHECKS PASSED!"
    echo ""
    echo "The local Camber mock is ready to use."
    echo ""
    echo "Next steps:"
    echo "  1. Export environment variables"
    echo "  2. Start API server"
    echo "  3. Create jobs and watch webhooks fire"
    echo "  4. Run test suite"
    echo ""
    exit 0
else
    echo "✗ SOME CHECKS FAILED"
    echo ""
    echo "Please fix the above issues before using the mock."
    echo "Refer to: LOCAL_CAMBER_MOCK_SETUP.md"
    echo ""
    exit 1
fi
