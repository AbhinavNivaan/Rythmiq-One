#!/bin/bash
# Deployment Configuration Template
# Copy and customize for your environment

################################################################################
# HEROKU DEPLOYMENT
################################################################################

# Option 1: Deploy to Heroku
heroku_deploy() {
  APP_NAME="rythmiq-phase1.5-trackc"
  
  # Create app
  heroku create "$APP_NAME"
  
  # Set environment variables
  heroku config:set \
    DATABASE_URL="${DATABASE_URL}" \
    JWT_PUBLIC_KEY="${JWT_PUBLIC_KEY}" \
    NODE_ENV="production" \
    EXECUTION_BACKEND="heroku" \
    HEROKU_API_KEY="${HEROKU_API_KEY}" \
    -a "$APP_NAME"
  
  # Deploy
  git push heroku main
  
  # Scale
  heroku ps:scale web=1 worker=1 -a "$APP_NAME"
  
  # Verify
  heroku logs --tail -a "$APP_NAME"
}

################################################################################
# DIGITALOCEAN APP PLATFORM DEPLOYMENT
################################################################################

# Option 2: Deploy to DigitalOcean App Platform (API Gateway)
do_app_platform_deploy() {
  # Create app.yaml first (see DEPLOYMENT.md)
  
  doctl apps create --spec app.yaml
  
  # Or update existing app
  # doctl apps update <app-id> --spec app.yaml
  
  # Monitor
  # doctl apps logs <app-id> --follow
}

################################################################################
# DIGITALOCEAN DROPLET DEPLOYMENT (WORKER)
################################################################################

# Option 3: Deploy to DigitalOcean Droplet
do_droplet_deploy() {
  DROPLET_IP="$1"
  
  # SSH and setup
  ssh root@"$DROPLET_IP" << 'EOF'
    # Update system
    apt update && apt upgrade -y
    
    # Install Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    
    # Create artifact directory
    mkdir -p /data/artifacts
    chmod 755 /data/artifacts
  EOF
  
  # Copy code
  scp -r . root@"$DROPLET_IP":/app
  
  # Build and run
  ssh root@"$DROPLET_IP" << 'EOF'
    cd /app
    
    # Build image
    docker build -f Dockerfile.worker -t rythmiq-worker:latest .
    
    # Create .env file
    cat > /app/.env.worker << 'ENVEOF'
      EXECUTION_BACKEND=do
      DATABASE_URL=postgresql://...
      ARTIFACT_STORE=/data/artifacts
      NODE_ENV=production
    ENVEOF
    
    # Run container
    docker run -d \
      --name worker \
      --env-file /app/.env.worker \
      -v /data/artifacts:/data/artifacts \
      --restart unless-stopped \
      ryth miq-worker:latest
    
    # Verify
    docker logs worker
  EOF
}

################################################################################
# LOCAL DOCKER TESTING
################################################################################

# Option 4: Test locally with Docker Compose
local_test() {
  cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: dev
      POSTGRES_DB: rythmiq
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  api:
    build:
      context: .
      dockerfile: Dockerfile.api-gateway
    ports:
      - "3000:3000"
    environment:
      DATABASE_URL: "postgres://app:dev@postgres:5432/rythmiq"
      JWT_PUBLIC_KEY: "test-key"
      NODE_ENV: "development"
    depends_on:
      - postgres

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    ports:
      - "3001:3001"
    environment:
      DATABASE_URL: "postgres://app:dev@postgres:5432/rythmiq"
      ARTIFACT_STORE: "/data/artifacts"
      EXECUTION_BACKEND: "local"
      NODE_ENV: "development"
    volumes:
      - ./artifacts:/data/artifacts
    depends_on:
      - postgres

volumes:
  postgres_data:
EOF

  docker-compose up
}

################################################################################
# VERIFICATION COMMANDS
################################################################################

# Test health endpoints
test_health() {
  echo "Testing API Gateway health..."
  curl http://localhost:3000/health
  
  echo -e "\nTesting Worker health..."
  curl http://localhost:3001/health
}

# Test upload endpoint
test_upload() {
  echo "Testing upload endpoint..."
  curl -X POST http://localhost:3000/upload \
    -H "Authorization: Bearer test-token" \
    -H "Content-Type: application/octet-stream" \
    --data-binary @sample.pdf
}

################################################################################
# MAIN
################################################################################

if [ "$1" = "heroku" ]; then
  heroku_deploy
elif [ "$1" = "do-app" ]; then
  do_app_platform_deploy
elif [ "$1" = "do-droplet" ]; then
  do_droplet_deploy "$2"
elif [ "$1" = "local" ]; then
  local_test
elif [ "$1" = "test" ]; then
  test_health
elif [ "$1" = "test-upload" ]; then
  test_upload
else
  echo "Usage: $0 {heroku|do-app|do-droplet <ip>|local|test|test-upload}"
fi
