#!/usr/bin/env bash
set -euo pipefail

# End-to-end encryption flow test for Rythmiq One
#
# What this script does:
# 1) Calls API to discover an active portal schema
# 2) Creates a job (POST /jobs)
# 3) Uploads a sample file to the returned presigned URL
# 4) Polls job status until completed/failed
# 5) Fetches output metadata
# 6) Checks worker logs for raw-upload cleanup evidence
#
# Required env vars:
#   API_BASE_URL   e.g. https://<your-api-service>
#   AUTH_BEARER    Supabase access token (JWT)
#
# Optional env vars:
#   SAMPLE_FILE    path to file to upload (default: /tmp/rythmiq-encryption-test.txt)
#   WORKER_SERVICE Cloud Run worker service name (default: rythmiq-worker)
#   GCP_REGION     Cloud Run region (default: asia-south1)
#   POLL_MAX_SECS  Poll timeout in seconds (default: 300)
#
# Usage:
#   chmod +x scripts/test_encryption_flow.sh
#   API_BASE_URL="https://api.example.com" AUTH_BEARER="<jwt>" ./scripts/test_encryption_flow.sh

API_BASE_URL="${API_BASE_URL:-}"
AUTH_BEARER="${AUTH_BEARER:-}"
SAMPLE_FILE="${SAMPLE_FILE:-/tmp/rythmiq-encryption-test.png}"
WORKER_SERVICE="${WORKER_SERVICE:-rythmiq-worker}"
GCP_REGION="${GCP_REGION:-asia-south1}"
POLL_MAX_SECS="${POLL_MAX_SECS:-300}"

if [[ -z "$API_BASE_URL" ]]; then
  echo "ERROR: API_BASE_URL is required"
  exit 1
fi

if [[ -z "$AUTH_BEARER" ]]; then
  echo "ERROR: AUTH_BEARER is required"
  exit 1
fi

# Normalize base URL
API_BASE_URL="${API_BASE_URL%/}"

if [[ ! -f "$SAMPLE_FILE" ]]; then
  echo "Creating sample PNG file at $SAMPLE_FILE"
  # 1x1 transparent PNG
  base64 -d > "$SAMPLE_FILE" <<'B64'
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2jQAAAAASUVORK5CYII=
B64
fi

FILE_NAME="$(basename "$SAMPLE_FILE")"
case "${FILE_NAME##*.}" in
  jpg|jpeg|JPG|JPEG) MIME_TYPE="image/jpeg" ;;
  png|PNG) MIME_TYPE="image/png" ;;
  pdf|PDF) MIME_TYPE="application/pdf" ;;
  *)
    echo "ERROR: SAMPLE_FILE must be .jpg, .jpeg, .png, or .pdf"
    exit 1
    ;;
esac
FILE_SIZE="$(wc -c < "$SAMPLE_FILE" | tr -d ' ')"

echo "==> 1/6 Fetching active portal schema"
SCHEMA_JSON="$(curl -sS -X GET "$API_BASE_URL/portal-schemas" \
  -H "Authorization: Bearer $AUTH_BEARER" \
  -H "Accept: application/json")"

SCHEMA_NAME="$(python - <<'PY' "$SCHEMA_JSON"
import json, sys
payload = json.loads(sys.argv[1])
schemas = payload.get("schemas", [])
print(schemas[0]["name"] if schemas else "")
PY
)"

if [[ -z "$SCHEMA_NAME" ]]; then
  echo "ERROR: No active portal schemas found or auth failed. Response:"
  echo "$SCHEMA_JSON"
  exit 1
fi

echo "Using portal schema: $SCHEMA_NAME"

echo "==> 2/6 Creating job"
CREATE_REQ="$(python - <<'PY' "$SCHEMA_NAME" "$FILE_NAME" "$MIME_TYPE" "$FILE_SIZE"
import json, sys
print(json.dumps({
  "portal_schema_name": sys.argv[1],
  "filename": sys.argv[2],
  "mime_type": sys.argv[3],
  "file_size_bytes": int(sys.argv[4]),
}))
PY
)"

CREATE_RESP="$(curl -sS -X POST "$API_BASE_URL/jobs" \
  -H "Authorization: Bearer $AUTH_BEARER" \
  -H "Content-Type: application/json" \
  -d "$CREATE_REQ")"

JOB_ID="$(python - <<'PY' "$CREATE_RESP"
import json, sys
obj = json.loads(sys.argv[1])
print(obj.get("job_id", ""))
PY
)"

UPLOAD_URL="$(python - <<'PY' "$CREATE_RESP"
import json, sys
obj = json.loads(sys.argv[1])
print(obj.get("upload_url", ""))
PY
)"

if [[ -z "$JOB_ID" || -z "$UPLOAD_URL" ]]; then
  echo "ERROR: Failed to create job. Response:"
  echo "$CREATE_RESP"
  exit 1
fi

echo "Created job: $JOB_ID"

echo "==> 3/6 Uploading sample file via presigned URL"
UPLOAD_HTTP_CODE="$(curl -sS -o /tmp/rythmiq_upload_resp.txt -w "%{http_code}" \
  -X PUT "$UPLOAD_URL" \
  -H "Content-Type: $MIME_TYPE" \
  --data-binary "@$SAMPLE_FILE")"

echo "Upload HTTP status: $UPLOAD_HTTP_CODE"
if [[ "$UPLOAD_HTTP_CODE" != "200" ]]; then
  echo "ERROR: Upload failed"
  cat /tmp/rythmiq_upload_resp.txt || true
  exit 1
fi

echo "==> 4/6 Polling job status"
START_TS="$(date +%s)"
FINAL_STATUS=""
DOWNLOAD_URL=""

while true; do
  NOW_TS="$(date +%s)"
  ELAPSED="$((NOW_TS - START_TS))"
  if (( ELAPSED > POLL_MAX_SECS )); then
    echo "ERROR: Timed out waiting for job completion ($POLL_MAX_SECS s)"
    exit 1
  fi

  STATUS_RESP="$(curl -sS -X GET "$API_BASE_URL/jobs/$JOB_ID" \
    -H "Authorization: Bearer $AUTH_BEARER" \
    -H "Accept: application/json")"

  FINAL_STATUS="$(python - <<'PY' "$STATUS_RESP"
import json, sys
obj = json.loads(sys.argv[1])
print(obj.get("status", ""))
PY
)"

  DOWNLOAD_URL="$(python - <<'PY' "$STATUS_RESP"
import json, sys
obj = json.loads(sys.argv[1])
print(obj.get("download_url", ""))
PY
)"

  echo "Status: ${FINAL_STATUS:-unknown} (t=${ELAPSED}s)"

  if [[ "$FINAL_STATUS" == "completed" ]]; then
    break
  fi

  if [[ "$FINAL_STATUS" == "failed" ]]; then
    echo "ERROR: Job failed"
    echo "$STATUS_RESP"
    exit 1
  fi

  sleep 5
done

echo "==> 5/6 Fetching output metadata"
OUTPUT_RESP="$(curl -sS -X GET "$API_BASE_URL/jobs/$JOB_ID/output" \
  -H "Authorization: Bearer $AUTH_BEARER" \
  -H "Accept: application/json")"

echo "Output response (truncated):"
echo "$OUTPUT_RESP" | head -c 500; echo

if [[ -n "$DOWNLOAD_URL" ]]; then
  echo "Output download URL exists: yes"
else
  echo "Output download URL exists: no (still acceptable if generated on-demand)"
fi

echo "==> 6/6 Checking worker logs for cleanup/redaction evidence"
if command -v gcloud >/dev/null 2>&1; then
  LOG_SNIPPET="$(gcloud run services logs read "$WORKER_SERVICE" --region "$GCP_REGION" --limit=200 2>/dev/null || true)"

  if echo "$LOG_SNIPPET" | grep -q "$JOB_ID"; then
    echo "Found logs for job_id: $JOB_ID"
  else
    echo "WARN: Could not find job_id in last 200 worker log lines"
  fi

  if echo "$LOG_SNIPPET" | grep -qi "Successfully deleted raw upload"; then
    echo "Raw upload cleanup evidence: FOUND"
  else
    echo "WARN: Raw upload cleanup message not found in recent logs"
  fi

  if echo "$LOG_SNIPPET" | grep -qi "REDACTED"; then
    echo "Log redaction evidence: FOUND"
  else
    echo "WARN: Redaction marker not found in recent logs"
  fi
else
  echo "gcloud not installed; skipping log checks"
fi

echo
echo "✅ Encryption flow test finished"
echo "   job_id: $JOB_ID"
echo "   final_status: $FINAL_STATUS"
