# Docker Testing Instructions

## Quick Test on Fresh VM

### 1. Clone and Setup
```bash
git clone https://github.com/yourusername/reddit-monitor-fresh.git
cd reddit-monitor-fresh
git checkout feature/native-development
```

### 2. Create Environment File
```bash
cp .env.production.example .env.production
```

Edit `.env.production` with your actual API keys:
- `REDDIT_CLIENT_ID=your_client_id`
- `REDDIT_CLIENT_SECRET=your_client_secret`
- `REDDIT_USERNAME=your_username`
- `REDDIT_PASSWORD=your_password`
- `TOGETHER_API_KEY=your_together_key`
- `BRAVE_API_KEY=your_brave_key`

### 3. Run with Docker Compose
```bash
docker-compose -f docker-compose.production.yml up --build
```

### 4. Test Access
- Frontend: http://localhost
- Backend API: http://localhost:5151/health
- Database: localhost:5443 (if you need direct access)

### 5. Stop
```bash
docker-compose -f docker-compose.production.yml down
```

## That's It!

No deployment scripts, no SSL, no complex setup. Just Docker containers running your current branch with Together AI integration.