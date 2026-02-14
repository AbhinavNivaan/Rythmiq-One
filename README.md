# Rythmiq One

**One-tap document preparation for exam portals**

Rythmiq One helps students prepare photos, signatures, and documents that meet exact portal requirements for competitive exams like NEET, JEE, CAT, and more.

## 🎯 Overview

- **Capture** → Take photos/signatures with your camera
- **Master Doc** → Auto-enhance and store as high-quality master
- **Adapt** → One-tap format for any exam portal
- **Download** → Get portal-ready files instantly

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Mobile App    │────▶│   API Gateway   │────▶│     Worker      │
│  (React Native) │     │    (FastAPI)    │     │    (Python)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │
         │                       ▼                       │
         │              ┌─────────────────┐              │
         │              │    Supabase     │              │
         │              │   (Auth + DB)   │              │
         │              └─────────────────┘              │
         │                                               │
         │              ┌─────────────────┐              │
         └─────────────▶│ DigitalOcean    │◀─────────────┘
                        │    Spaces       │
                        └─────────────────┘
```

## 📁 Project Structure

```
rythmiq-one/
├── app-v2/                 # React Native mobile app
│   ├── app/                # Expo Router screens
│   ├── components/         # Reusable UI components
│   ├── hooks/              # Custom React hooks
│   ├── services/           # API & storage services
│   └── config/             # App configuration
│
├── app/                    # FastAPI backend
│   ├── api/                # API routes
│   │   ├── middleware/     # Rate limiting, auth
│   │   └── routers/        # Route handlers
│   └── main.py             # App entry point
│
├── worker/                 # Processing worker
│   ├── core/               # Core processing logic
│   └── worker.py           # STDIN→STDOUT worker
│
├── engine/                 # Image processing engine
│   ├── enhance.py          # Quality enhancement
│   ├── adapt.py            # Schema adaptation
│   └── validate.py         # Quality validation
│
├── schemas/                # Portal schema definitions
│   └── portals/            # Per-portal requirements
│
├── db/                     # Database migrations
│   └── schema.sql          # Supabase schema + RLS
│
├── tests/                  # Test suites
│   ├── api/                # API integration tests
│   ├── worker/             # Worker contract tests
│   ├── ui/                 # UI component tests
│   └── performance/        # Performance benchmarks
│
├── scripts/                # Deployment scripts
├── docs/                   # Additional documentation
└── infra/                  # Infrastructure configs
```

## 🚀 Getting Started

### Prerequisites

- Node.js 18+ and pnpm
- Python 3.11+
- Docker & Docker Compose
- Expo CLI (`npm install -g expo-cli`)
- EAS CLI (`npm install -g eas-cli`)

### Environment Setup

```bash
# Clone the repository
git clone <repo-url>
cd rythmiq-one

# Copy environment template
cp .env.example .env

# Edit .env with your credentials
# See ENV_REFERENCE.md for all variables
```

### Mobile App (app-v2)

```bash
cd app-v2

# Install dependencies
pnpm install

# Start development server
pnpm start

# Run on iOS simulator
pnpm ios

# Run on Android emulator
pnpm android
```

### Backend API

```bash
# Start all services with Docker
docker-compose up -d

# Or run locally
cd app
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### Worker

```bash
cd worker
pip install -r requirements.txt

# Test worker locally
echo '{"job_id": "test", "job_type": "process"}' | python worker.py
```

## 🧪 Running Tests

```bash
# All tests
pytest

# API tests only
pytest tests/api/ -v

# Worker tests only
pytest tests/worker/ -v

# With coverage
pytest --cov=app --cov=worker --cov-report=html
```

## 📱 Mobile App Details

### Tech Stack

- **Framework**: React Native with Expo SDK 54
- **Navigation**: Expo Router (file-based)
- **State**: @tanstack/react-query
- **Styling**: StyleSheet (dark theme)
- **Icons**: lucide-react-native

### Theme Colors

```typescript
const colors = {
  inkBlack: '#070712',    // Primary background
  mayaBlue: '#89C7FE',    // Accent/highlight
  trueCobalt: '#1A2595',  // Buttons/CTAs
  shadowGrey: '#191B26',  // Cards/surfaces
  white: '#FCFEFF',       // Text/icons
};
```

### Key Screens

| Screen | Path | Description |
|--------|------|-------------|
| Login | `/login` | Phone + OTP authentication |
| Vault | `/(tabs)/vault` | Document gallery |
| Camera | `/(tabs)/camera` | Document capture |
| Processing | `/(tabs)/processing` | Upload progress |
| Job Detail | `/(tabs)/job-detail` | Result & download |
| Portal Selector | `/(tabs)/portal-selector` | Choose target portal |
| Adapt Status | `/(tabs)/adapt-status` | Adaptation progress |

## 🔌 API Reference

### Authentication

```
POST /api/auth/request-otp
POST /api/auth/verify-otp
POST /api/auth/refresh
DELETE /api/auth/logout
```

### Jobs

```
GET  /api/jobs           # List user's jobs
POST /api/jobs           # Create new job
GET  /api/jobs/{id}      # Get job details
GET  /api/jobs/{id}/download  # Get download URL
```

### Schema Adaptation

```
POST /api/adapt          # Start adaptation job
GET  /api/adapt/{id}     # Check adaptation status
```

### Schemas

```
GET /api/schemas/portals        # List available portals
GET /api/schemas/{portal_id}    # Get portal requirements
```

See [API_GATEWAY_QUICKSTART.md](./API_GATEWAY_QUICKSTART.md) for full documentation.

## 🔒 Security

- **Authentication**: Supabase Auth with phone OTP
- **Session Management**: JWT with 24-hour expiry, secure refresh
- **Storage**: expo-secure-store for tokens
- **Biometric**: Face ID / Touch ID for app unlock
- **Rate Limiting**: Per-endpoint limits (see rate_limit.py)
- **RLS**: Row-Level Security on all Supabase tables

## 📦 Deployment

### Mobile App (EAS Build)

```bash
cd app-v2

# Build for TestFlight
eas build --platform ios --profile preview

# Build for production
eas build --platform ios --profile production

# Submit to App Store
eas submit --platform ios
```

### Backend (Docker)

```bash
# Build images
docker build -t rythmiq-api -f Dockerfile .
docker build -t rythmiq-worker -f Dockerfile.worker .

# Deploy to your container platform
# See DEPLOYMENT.md for cloud-specific guides
```

## 🗺️ Roadmap

### Phase 1 (Current) ✅
- Core capture & processing flow
- Master document storage
- Schema adaptation for top 10 portals
- iOS app

### Phase 2 (Planned)
- Android app
- Face detection & auto-crop
- Signature extraction from full page
- Batch document processing

### Phase 3 (Future)
- AI-powered form filling
- Multi-language support
- Enterprise/institutional accounts

## 📄 License

Proprietary - All rights reserved

## 🤝 Contributing

Internal team only. See CONTRIBUTING.md for guidelines.

## 📞 Support

- Email: support@rythmiq.one
- Docs: https://docs.rythmiq.one
