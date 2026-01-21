################################################################################
# Execution Backend Deployment Notes
# This Dockerfile supports deployment to DigitalOcean and Heroku
# Select backend via EXECUTION_BACKEND environment variable
################################################################################

FROM node:18-alpine AS builder

WORKDIR /app

# Install build dependencies
RUN apk add --no-cache python3 make g++

# Copy source files
COPY package*.json ./
RUN npm ci --only=production

# Build TypeScript
COPY tsconfig.json ./
COPY src/ ./src/
RUN npm run build

################################################################################
# Production Image
################################################################################

FROM node:18-alpine

WORKDIR /app

# Install runtime dependencies only
RUN apk add --no-cache curl

# Copy built artifacts and runtime dependencies
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY package*.json ./

# Health check for container orchestration
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "const http = require('http'); http.get('http://localhost:3000/health', (res) => { if (res.statusCode === 200) process.exit(0); else process.exit(1); })"

# Set default execution backend
ENV EXECUTION_BACKEND=local

################################################################################
# EXECUTION BACKEND ENVIRONMENT VARIABLES
#
# Set EXECUTION_BACKEND to select the execution target:
#   - local:  Run jobs locally on this container (default)
#   - camber: Delegate to Camber Cloud
#   - do:     Delegate to DigitalOcean Apps/Functions
#   - heroku: Delegate to Heroku Dynos
#
################################################################################

# ============================================================================
# LOCAL BACKEND (Default)
# No additional environment variables required
# ============================================================================
# Example: EXECUTION_BACKEND=local


# ============================================================================
# CAMBER BACKEND
# Required environment variables:
#   CAMBER_API_KEY          - API key for Camber Cloud
#   CAMBER_API_ENDPOINT     - Camber API endpoint (default: https://api.camber.cloud)
#   CAMBER_EXECUTION_REGION - Execution region (default: us-east-1)
#   CAMBER_QUEUE_NAME       - Job queue name (default: default)
#   CAMBER_EXECUTION_TIMEOUT_MS - Job timeout in ms (default: 300000)
# ============================================================================
# Example:
# ENV EXECUTION_BACKEND=camber
# ENV CAMBER_API_KEY=sk-xxxxxxxxxxxx
# ENV CAMBER_EXECUTION_REGION=us-west-2
# ENV CAMBER_QUEUE_NAME=high-priority


# ============================================================================
# DIGITALOCEAN BACKEND
# Required environment variables:
#   DO_API_TOKEN             - DigitalOcean API token
#   DO_API_ENDPOINT          - DO API endpoint (default: https://api.digitalocean.com/v2)
#   DO_APP_NAME              - DO App Platform app name (default: rythmiq-execution)
#   DO_EXECUTION_REGION      - Execution region (default: nyc)
#   DO_FUNCTION_MEMORY_MB    - Function memory in MB (default: 256)
#   DO_EXECUTION_TIMEOUT_MS  - Job timeout in ms (default: 300000)
#
# Deployment to DigitalOcean App Platform:
#   1. Create app.yaml in root (see DO_APP_YAML below)
#   2. Deploy: doctl apps create --spec app.yaml
#   3. Set environment variables via DigitalOcean console or CLI
#   4. Redeploy with: doctl apps update <app-id> --spec app.yaml
#
# ============================================================================
# Example:
# ENV EXECUTION_BACKEND=do
# ENV DO_API_TOKEN=dop_v1_xxxxxxxxxxxx
# ENV DO_APP_NAME=rythmiq-exec-worker
# ENV DO_EXECUTION_REGION=sfo


# ============================================================================
# HEROKU BACKEND
# Required environment variables:
#   HEROKU_API_KEY          - Heroku API authentication token
#   HEROKU_API_ENDPOINT     - Heroku API endpoint (default: https://api.heroku.com)
#   HEROKU_APP_NAME         - Heroku app name (default: rythmiq-execution)
#   HEROKU_DYNO_TYPE        - Dyno type: worker, web, scheduler (default: worker)
#   HEROKU_DYNO_SIZE        - Dyno size: free, hobby, standard-1x, etc. (default: standard-1x)
#   HEROKU_EXECUTION_TIMEOUT_MS - Job timeout in ms (default: 300000)
#
# Deployment to Heroku:
#   1. Create Heroku app: heroku create rythmiq-execution
#   2. Deploy: git push heroku main
#   3. Set environment variables:
#      heroku config:set EXECUTION_BACKEND=heroku \
#                       HEROKU_API_KEY=<your-api-key> \
#                       HEROKU__SIZE=standard-2x -a rythmiq-execution
#   4. Scale worker dynos: heroku ps:scale worker=2 -a rythmiq-execution
#
# Procfile (required in repo root for Heroku):
#   web: npm run start
#   worker: npm run worker
#
# ============================================================================
# Example:
# ENV EXECUTION_BACKEND=heroku
# ENV HEROKU_API_KEY=<api-token>
# ENV HEROKU_DYNO_SIZE=standard-2x
# ENV HEROKU_DYNO_TYPE=worker


# ============================================================================
# DIGITALOCEAN APP PLATFORM SPEC (app.yaml)
# ============================================================================
# name: rythmiq-execution
# regions:
#   - name: nyc
# services:
#   - name: execution-worker
#     github:
#       repo: your-org/rythmiq-one
#       branch: main
#       deploy_on_push: true
#     build_command: npm ci && npm run build
#     run_command: npm start
#     envs:
#       - key: EXECUTION_BACKEND
#         value: do
#       - key: DO_API_TOKEN
#         scope: RUN_AND_BUILD_TIME
#         value: ${DO_API_TOKEN}
#       - key: DO_APP_NAME
#         value: rythmiq-execution
#       - key: DO_EXECUTION_REGION
#         value: nyc
#     resources:
#       memory_mb: 512
#       cpu_count: 1
#     http_port: 3000
#     health_check:
#       http_path: /health
#       period_seconds: 30
#
# ============================================================================


EXPOSE 3000

CMD ["npm", "start"]
