#!/usr/bin/env bash
#
# LOCAL CAMBER MOCK - QUICK START
#
# This script demonstrates how to:
# 1. Start the API with local mock
# 2. Create a job
# 3. Wait for webhook
# 4. Retrieve results
#
# Usage:
#   bash scripts/run_local_mock_demo.sh
#

set -e

echo "=========================================="
echo "LOCAL CAMBER MOCK - QUICK START DEMO"
echo "=========================================="
echo ""

# Configuration
API_HOST="127.0.0.1"
API_PORT="8000"
API_URL="http://${API_HOST}:${API_PORT}"
WEBHOOK_SECRET="test-webhook-secret-12345"

echo "[1/5] Environment Setup"
echo "-------"
export EXECUTION_BACKEND=local
export WEBHOOK_SECRET="${WEBHOOK_SECRET}"
export SERVICE_ENV=dev
export API_PORT="${API_PORT}"
echo "✓ EXECUTION_BACKEND=local"
echo "✓ WEBHOOK_SECRET=${WEBHOOK_SECRET}"
echo "✓ SERVICE_ENV=dev"
echo ""

echo "[2/5] Start FastAPI Server"
echo "-------"
echo "Starting: uvicorn app.api.main:app --host ${API_HOST} --port ${API_PORT} --reload"
echo "Note: In real setup, run this in a separate terminal"
echo ""

echo "[3/5] Create a Job"
echo "-------"
JOB_RESPONSE=$(curl -s -X POST "${API_URL}/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "portal_schema_name": "invoice",
    "filename": "test-invoice.pdf",
    "mime_type": "application/pdf",
    "file_size_bytes": 50000
  }')

echo "Request: POST /jobs"
echo "Response:"
echo "${JOB_RESPONSE}" | jq '.' || echo "${JOB_RESPONSE}"
echo ""

# Extract job_id from response
JOB_ID=$(echo "${JOB_RESPONSE}" | jq -r '.job_id' 2>/dev/null || echo "")

if [ -z "${JOB_ID}" ] || [ "${JOB_ID}" == "null" ]; then
  echo "❌ Failed to create job"
  exit 1
fi

echo "✓ Job created: ${JOB_ID}"
echo ""

echo "[4/5] Wait for Mock Camber Processing"
echo "-------"
echo "Waiting 2 seconds for webhook callback..."
sleep 2
echo "✓ Mock should have processed and sent webhook"
echo ""

echo "[5/5] Check Job Status"
echo "-------"
echo "Request: GET /jobs/${JOB_ID}"
STATUS_RESPONSE=$(curl -s -X GET "${API_URL}/jobs/${JOB_ID}")

echo "Response:"
echo "${STATUS_RESPONSE}" | jq '.' || echo "${STATUS_RESPONSE}"
echo ""

# Check if completed
JOB_STATUS=$(echo "${STATUS_RESPONSE}" | jq -r '.status' 2>/dev/null || echo "")

if [ "${JOB_STATUS}" == "completed" ]; then
  echo "✓ Job completed successfully!"
else
  echo "⚠ Job status: ${JOB_STATUS} (may still be processing)"
fi

echo ""
echo "=========================================="
echo "DEMO COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Retrieve results: GET /jobs/${JOB_ID}/output"
echo "2. Run tests: pytest tests/test_e2e_pipeline.py -v"
echo "3. Check logs for [MOCK CAMBER] messages"
echo ""
