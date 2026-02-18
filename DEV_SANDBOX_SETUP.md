# Dev Sandbox Setup Guide

## Quick Start

The Dev Sandbox mode allows you to test the full Rythmiq pipeline with production-grade processing while bypassing authentication.

### What Dev Sandbox Does

1. **Auth Bypass**: No login required - uses a static dev user ID
2. **24h Storage TTL**: Uploaded files are stored in a separate `dev-sandbox/` prefix and expire after 24 hours
3. **Production Pipelines**: All Camber processing uses the exact same flow as production
4. **Visual Indicator**: Orange "🧪 Dev Sandbox Mode" banner shows in the app

### Setup Steps

#### 1. Run the Database Migration

Go to your Supabase SQL Editor and run:

```sql
-- Copy the contents of: db/migrations/002_add_portal_schema_columns.sql
```

This adds the required columns and seeds portal schemas.

#### 2. Start the Backend

```bash
cd "/Users/abhinav/Rythmiq One"
source .venv/bin/activate
uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```

The backend `.env` already has:
- `DEV_SANDBOX_ENABLED=true`
- `SERVICE_ENV=dev`
- `DEV_SANDBOX_STORAGE_TTL_HOURS=24`

#### 3. Set Up ngrok (for mobile access)

```bash
ngrok http 8000
```

Copy the ngrok URL (e.g., `https://abc123.ngrok-free.dev`)

#### 4. Update Mobile App Config

Edit `app-v2/.env`:

```dotenv
EXPO_PUBLIC_API_URL=https://your-ngrok-url.ngrok-free.dev
EXPO_PUBLIC_DEV_SANDBOX=true
```

#### 5. Start the Mobile App

```bash
cd app-v2
npx expo start --clear
```

Scan QR with Expo Go.

### Testing the Full Flow

1. **Open App** → You'll see the orange "🧪 Dev Sandbox Mode" banner
2. **Tap Scan** → Camera opens
3. **Take Photo** → Approve
4. **Select Document Type** → Photo, Signature, or Document
5. **Name It** → Optional name for the document
6. **Create Master** → Uploads to Camber for processing

The document is:
- Processed using production Camber pipelines
- Stored with 24-hour expiration
- Visible in the Jobs tab

### Verifying Dev Sandbox is Active

```bash
curl http://localhost:8000/health
```

Response when dev sandbox is enabled:
```json
{
  "status": "ok",
  "dev_sandbox": {
    "enabled": true,
    "storage_ttl_hours": 24,
    "message": "Dev sandbox mode active - auth bypassed, 24h storage TTL"
  }
}
```

### Disabling Dev Sandbox

To switch to production mode:

**Backend** (`.env`):
```dotenv
DEV_SANDBOX_ENABLED=false
SERVICE_ENV=prod
```

**Mobile** (`app-v2/.env`):
```dotenv
EXPO_PUBLIC_DEV_SANDBOX=false
```

### Storage Cleanup

Dev sandbox uploads go to `dev-sandbox/` prefix in DigitalOcean Spaces. You can set up a lifecycle policy to auto-delete objects older than 24 hours:

```bash
# DigitalOcean Spaces lifecycle policy (via S3 API)
aws s3api put-bucket-lifecycle-configuration \
  --bucket rythmiq-one-artifacts \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "dev-sandbox-cleanup",
      "Filter": {"Prefix": "dev-sandbox/"},
      "Status": "Enabled",
      "Expiration": {"Days": 1}
    }]
  }'
```

### Troubleshooting

**"Schema not found" error:**
Run the database migration to seed portal schemas.

**Mobile app shows auth error:**
Ensure `EXPO_PUBLIC_DEV_SANDBOX=true` in `app-v2/.env` and restart Expo with `--clear`.

**Backend not in dev sandbox mode:**
Check that both `DEV_SANDBOX_ENABLED=true` AND `SERVICE_ENV=dev` are set.
