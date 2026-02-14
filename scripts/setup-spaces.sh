#!/bin/bash
# ==============================================
# Rythmiq One - DigitalOcean Spaces Setup Script
# ==============================================
# This script configures the bucket structure and lifecycle rules
# Run once after creating your Spaces bucket
# ==============================================

set -e

# Configuration
SPACES_ENDPOINT="${DO_SPACES_ENDPOINT:-https://nyc3.digitaloceanspaces.com}"
SPACES_BUCKET="${DO_SPACES_BUCKET:-rythmiq-documents}"
REGION="${DO_SPACES_REGION:-nyc3}"

echo "🗄️  Configuring DigitalOcean Spaces: $SPACES_BUCKET"
echo "   Endpoint: $SPACES_ENDPOINT"
echo "   Region: $REGION"

# Check for required tools
if ! command -v aws &> /dev/null; then
    echo "❌ AWS CLI is required. Install with: brew install awscli"
    exit 1
fi

# Configure AWS CLI for Spaces
export AWS_ACCESS_KEY_ID="${DO_SPACES_ACCESS_KEY}"
export AWS_SECRET_ACCESS_KEY="${DO_SPACES_SECRET_KEY}"

ENDPOINT_URL="${SPACES_ENDPOINT/https:\/\//https:\/\/$SPACES_BUCKET.}"

echo ""
echo "📁 Creating folder structure..."

# Create folder structure by uploading empty marker files
echo "" | aws s3 cp - "s3://${SPACES_BUCKET}/raw/.keep" \
    --endpoint-url "$SPACES_ENDPOINT" \
    --acl private 2>/dev/null || true

echo "" | aws s3 cp - "s3://${SPACES_BUCKET}/master/.keep" \
    --endpoint-url "$SPACES_ENDPOINT" \
    --acl private 2>/dev/null || true

echo "" | aws s3 cp - "s3://${SPACES_BUCKET}/output/.keep" \
    --endpoint-url "$SPACES_ENDPOINT" \
    --acl private 2>/dev/null || true

echo "   ✅ Created /raw (encrypted uploads)"
echo "   ✅ Created /master (processed masters)"
echo "   ✅ Created /output (ephemeral ZIPs)"

# Set lifecycle rules for output folder (24-hour TTL)
echo ""
echo "⏰ Setting lifecycle rules for /output (24h TTL)..."

LIFECYCLE_CONFIG=$(cat <<EOF
{
    "Rules": [
        {
            "ID": "DeleteOutputAfter24Hours",
            "Status": "Enabled",
            "Filter": {
                "Prefix": "output/"
            },
            "Expiration": {
                "Days": 1
            }
        }
    ]
}
EOF
)

echo "$LIFECYCLE_CONFIG" > /tmp/lifecycle.json

aws s3api put-bucket-lifecycle-configuration \
    --bucket "$SPACES_BUCKET" \
    --lifecycle-configuration file:///tmp/lifecycle.json \
    --endpoint-url "$SPACES_ENDPOINT" 2>/dev/null || {
    echo "   ⚠️  Note: Lifecycle rules may need to be set via DO console"
    echo "      Set 'output/' prefix to expire after 1 day"
}

rm -f /tmp/lifecycle.json

# Set CORS policy
echo ""
echo "🌐 Setting CORS policy..."

CORS_CONFIG=$(cat <<EOF
{
    "CORSRules": [
        {
            "AllowedOrigins": ["*"],
            "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
            "AllowedHeaders": ["*"],
            "MaxAgeSeconds": 3600
        }
    ]
}
EOF
)

echo "$CORS_CONFIG" > /tmp/cors.json

aws s3api put-bucket-cors \
    --bucket "$SPACES_BUCKET" \
    --cors-configuration file:///tmp/cors.json \
    --endpoint-url "$SPACES_ENDPOINT" 2>/dev/null || {
    echo "   ⚠️  CORS may need to be set via DO console"
}

rm -f /tmp/cors.json

echo ""
echo "✅ DigitalOcean Spaces configuration complete!"
echo ""
echo "📋 Bucket Structure:"
echo "   $SPACES_BUCKET/"
echo "   ├── raw/          # Encrypted user uploads"
echo "   ├── master/       # Processed master documents"
echo "   └── output/       # Ephemeral ZIPs (24h TTL)"
echo ""
echo "🔐 Security Notes:"
echo "   - All files are private by default"
echo "   - Use pre-signed URLs for access"
echo "   - Output files auto-delete after 24 hours"
