# Deployment Guide

This guide covers deploying the Reddit Monitor system in different environments.

## 🏠 Local Development

### Quick Setup
```bash
# 1. Clone and setup
git clone <repo-url>
cd reddit-claim-verifier
cp .env.example .env

# 2. Edit .env with your credentials
nano .env

# 3. Start services
docker-compose up -d

# 4. Setup Ollama (separate terminals)
ollama pull llama3.1:8b llama3.1:70b
OLLAMA_HOST=0.0.0.0:8001 ollama serve &
OLLAMA_HOST=0.0.0.0:8002 ollama serve &

# 5. Test the system
python test_queue_system.py
```

### Development Workflow
```bash
# Backend development
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 5151

# Frontend development  
cd frontend
npm install
npm run dev

# Database management
docker-compose up -d db
# Connect: localhost:5443, user: redditmon, db: redditmon
```

## 🐳 Docker Production

### Full Docker Deployment
```bash
# 1. Prepare environment
cp .env.production .env
# Edit with production credentials

# 2. Build and deploy
docker-compose -f docker-compose.prod.yml up -d

# 3. Monitor services
docker-compose logs -f
```

### Production Docker Compose
Create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    networks:
      - reddit_monitor_network

  backend:
    build: 
      context: ./backend
      dockerfile: Dockerfile.prod
    restart: unless-stopped
    environment:
      - NODE_ENV=production
      - DB_HOST=db
      - DB_PORT=5432
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - REDDIT_CLIENT_ID=${REDDIT_CLIENT_ID}
      - REDDIT_CLIENT_SECRET=${REDDIT_CLIENT_SECRET}
      - REDDIT_USERNAME=${REDDIT_USERNAME}
      - REDDIT_PASSWORD=${REDDIT_PASSWORD}
      - BRAVE_API_KEY=${BRAVE_API_KEY}
      - TRIAGE_ENDPOINT=${TRIAGE_ENDPOINT}
      - RESEARCH_ENDPOINT=${RESEARCH_ENDPOINT}
      - RESPONSE_ENDPOINT=${RESPONSE_ENDPOINT}
      - EDITORIAL_ENDPOINT=${EDITORIAL_ENDPOINT}
    depends_on:
      - db
    networks:
      - reddit_monitor_network
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.backend.rule=Host(`api.yourcomputersailor.com`)"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.prod
    restart: unless-stopped
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.frontend.rule=Host(`app.yourcomputersailor.com`)"
    networks:
      - reddit_monitor_network

  # Reverse proxy
  traefik:
    image: traefik:v2.9
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - ./traefik:/etc/traefik
    networks:
      - reddit_monitor_network

volumes:
  postgres_data:

networks:
  reddit_monitor_network:
    external: false
```

## ☁️ Cloud Deployment

### AWS ECS Deployment

#### Prerequisites
- AWS CLI configured
- ECS cluster created
- RDS PostgreSQL instance
- Application Load Balancer

#### Steps
1. **Build and push images**:
```bash
# Build images
docker build -t reddit-claim-verifier-backend ./backend
docker build -t reddit-claim-verifier-frontend ./frontend

# Tag for ECR
docker tag reddit-monitor-backend:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/reddit-monitor-backend:latest
docker tag reddit-monitor-frontend:latest 123456789012.dkr.ecr.us-east-1.amazonaws.com/reddit-monitor-frontend:latest

# Push to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/reddit-monitor-backend:latest
docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/reddit-monitor-frontend:latest
```

2. **Create task definition** (`task-definition.json`):
```json
{
  "family": "reddit-claim-verifier",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "containerDefinitions": [
    {
      "name": "backend",
      "image": "123456789012.dkr.ecr.us-east-1.amazonaws.com/reddit-monitor-backend:latest",
      "portMappings": [{"containerPort": 5151}],
      "environment": [
        {"name": "DB_HOST", "value": "your-rds-endpoint"},
        {"name": "DB_NAME", "value": "redditmon"},
        {"name": "DB_USER", "value": "redditmon"},
        {"name": "DB_PASSWORD", "value": "your-secure-password"},
        {"name": "REDDIT_CLIENT_ID", "value": "your-client-id"},
        {"name": "BRAVE_API_KEY", "value": "your-brave-key"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/reddit-monitor",
          "awslogs-region": "us-east-1"
        }
      }
    }
  ]
}
```

3. **Deploy service**:
```bash
# Register task definition
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Create service
aws ecs create-service \
    --cluster reddit-monitor-cluster \
    --service-name reddit-monitor-service \
    --task-definition reddit-monitor:1 \
    --desired-count 2 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[subnet-12345,subnet-67890],securityGroups=[sg-abcdef],assignPublicIp=ENABLED}"
```

### Google Cloud Run

```bash
# 1. Build and push to Container Registry
gcloud builds submit --tag gcr.io/your-project/reddit-monitor-backend ./backend
gcloud builds submit --tag gcr.io/your-project/reddit-monitor-frontend ./frontend

# 2. Deploy backend
gcloud run deploy reddit-monitor-backend \
    --image gcr.io/your-project/reddit-monitor-backend \
    --platform managed \
    --region us-central1 \
    --set-env-vars="DB_HOST=your-cloud-sql-ip,DB_NAME=redditmon,DB_USER=redditmon" \
    --set-secrets="DB_PASSWORD=reddit-monitor-db-password:latest,REDDIT_CLIENT_SECRET=reddit-client-secret:latest"

# 3. Deploy frontend
gcloud run deploy reddit-monitor-frontend \
    --image gcr.io/your-project/reddit-monitor-frontend \
    --platform managed \
    --region us-central1
```

## 🧠 LLM Infrastructure

### Self-Hosted Ollama

#### Single Server Setup
```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull models
ollama pull llama3.1:8b
ollama pull llama3.1:70b

# Setup systemd services
sudo tee /etc/systemd/system/ollama-fast.service << EOF
[Unit]
Description=Ollama Fast LLM Service
After=network.target

[Service]
Type=simple
User=ollama
Environment=OLLAMA_HOST=0.0.0.0:8001
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/ollama-capable.service << EOF
[Unit]
Description=Ollama Capable LLM Service  
After=network.target

[Service]
Type=simple
User=ollama
Environment=OLLAMA_HOST=0.0.0.0:8002
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now ollama-fast ollama-capable
```

#### Multi-Server Setup
```bash
# Server 1 (Fast processing) - 8GB+ RAM
OLLAMA_HOST=0.0.0.0:8001 ollama serve
ollama pull llama3.1:8b

# Server 2 (Capable processing) - 32GB+ RAM  
OLLAMA_HOST=0.0.0.0:8001 ollama serve
ollama pull llama3.1:70b

# Update environment variables
TRIAGE_ENDPOINT=http://fast-server:8001
EDITORIAL_ENDPOINT=http://fast-server:8001
RESEARCH_ENDPOINT=http://capable-server:8001
RESPONSE_ENDPOINT=http://capable-server:8001
```

### Cloud LLM Services

#### OpenAI API Integration
Update `backend/agents/base_agent.py` to support OpenAI:

```python
# Add OpenAI client option
import openai

class BaseAgent:
    def __init__(self, model: str, endpoint: str = None, provider: str = "ollama"):
        self.provider = provider
        if provider == "openai":
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        # ... existing code
```

## 🗄️ Database Management

### Production PostgreSQL

#### AWS RDS Setup
```bash
# Create RDS instance
aws rds create-db-instance \
    --db-instance-identifier reddit-monitor-db \
    --db-instance-class db.t3.medium \
    --engine postgres \
    --engine-version 16.1 \
    --master-username redditmon \
    --master-user-password "YourSecurePassword123" \
    --allocated-storage 100 \
    --storage-type gp2 \
    --vpc-security-group-ids sg-12345678 \
    --db-subnet-group-name reddit-monitor-subnet-group \
    --backup-retention-period 7 \
    --storage-encrypted
```

#### Backup Strategy
```bash
# Daily backups
0 2 * * * pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME | gzip > /backups/reddit_monitor_$(date +\%Y\%m\%d).sql.gz

# Cleanup old backups (keep 30 days)
0 3 * * * find /backups -name "reddit_monitor_*.sql.gz" -mtime +30 -delete
```

## 📊 Monitoring & Logging

### Application Monitoring

#### Prometheus + Grafana
```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    volumes:
      - grafana_data:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

#### Application Metrics
Add to `backend/main.py`:
```python
from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Response

# Metrics
REQUEST_COUNT = Counter('http_requests_total', 'Total HTTP requests', ['method', 'endpoint'])
PROCESSING_TIME = Histogram('queue_processing_seconds', 'Time spent processing', ['stage'])

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

### Log Management

#### Centralized Logging
```bash
# ELK Stack for log aggregation
docker run -d --name elasticsearch \
  -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  docker.elastic.co/elasticsearch/elasticsearch:8.5.0

docker run -d --name kibana \
  -p 5601:5601 \
  --link elasticsearch:elasticsearch \
  docker.elastic.co/kibana/kibana:8.5.0
```

## 🔒 Security Hardening

### Environment Security
```bash
# Use Docker secrets for sensitive data
echo "your-secret-password" | docker secret create db_password -
echo "your-reddit-secret" | docker secret create reddit_secret -

# Update docker-compose to use secrets
services:
  backend:
    secrets:
      - db_password
      - reddit_secret
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password
      - REDDIT_CLIENT_SECRET_FILE=/run/secrets/reddit_secret
```

### Network Security
```bash
# Firewall rules (UFW)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow from 10.0.0.0/8 to any port 5432  # Database access from internal network only
sudo ufw enable
```

### SSL/TLS Configuration
```yaml
# traefik/traefik.yml
entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entrypoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: your-email@domain.com
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web
```

## 🚀 Performance Optimization

### Database Optimization
```sql
-- Create indexes for queue performance
CREATE INDEX CONCURRENTLY idx_posts_queue_processing ON posts (queue_stage, queue_status, assigned_at);
CREATE INDEX CONCURRENTLY idx_posts_priority ON posts ((metadata->>'priority'));
CREATE INDEX CONCURRENTLY idx_queue_results_lookup ON queue_results (post_id, stage, created_at);

-- Partition large tables by date
CREATE TABLE posts_y2024m01 PARTITION OF posts
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### Application Scaling
```bash
# Horizontal scaling with multiple backend instances
docker-compose up --scale backend=3

# Load balancer configuration
upstream backend {
    server backend_1:5151;
    server backend_2:5151;
    server backend_3:5151;
}
```

## 📋 Maintenance

### Regular Maintenance Tasks
```bash
#!/bin/bash
# maintenance.sh

# Cleanup old queue results (keep 30 days)
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "DELETE FROM queue_results WHERE created_at < NOW() - INTERVAL '30 days';"

# Vacuum database
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "VACUUM ANALYZE;"

# Restart services if needed
docker-compose restart backend

# Check disk space
df -h
```

### Health Checks
```bash
#!/bin/bash
# health-check.sh

# Check API health
curl -f http://localhost:5151/health || exit 1

# Check queue processing
QUEUE_STATUS=$(curl -s http://localhost:5151/queue/status | jq -r '.running')
if [ "$QUEUE_STATUS" != "true" ]; then
    echo "Queue not running"
    exit 1
fi

# Check database connection
psql -h $DB_HOST -U $DB_USER -d $DB_NAME -c "SELECT 1;" > /dev/null || exit 1

echo "All health checks passed"
```

## 🔄 Updates and Migrations

### Application Updates
```bash
# 1. Backup database
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > backup_$(date +%Y%m%d).sql

# 2. Pull latest changes
git pull origin main

# 3. Update dependencies
cd backend && pip install -r requirements.txt
cd ../frontend && npm install

# 4. Run migrations (if any)
python migrate.py

# 5. Restart services
docker-compose down
docker-compose up -d
```

This deployment guide provides comprehensive instructions for various deployment scenarios, from local development to production cloud deployments.