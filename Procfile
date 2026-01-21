# Heroku Procfile for Phase-1.5 Track C
# 
# Required Config Vars:
#   heroku config:set DATABASE_URL=<postgres-url>
#   heroku config:set JWT_PUBLIC_KEY=<public-key>
#   heroku config:set SERVICE_ENV=production
#   heroku config:set ARTIFACT_STORE_TYPE=s3
#   heroku config:set EXECUTION_BACKEND=cpu
#
# Deployment:
#   git push heroku main
#   heroku ps:scale web=1 worker=0
#
# Monitoring:
#   heroku logs --tail --app <app-name>
#   heroku ps --app <app-name>
#
# Health Check:
#   curl https://<app-name>.herokuapp.com/health
#   curl https://<app-name>.herokuapp.com/ready

web: node dist/api-gateway/server.js
