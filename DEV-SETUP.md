# Reddit Monitor - Native Development Setup

This guide covers running the Reddit Monitor application natively (without Docker for backend/frontend, but using Docker for PostgreSQL database only).

## Quick Start

1. **Start everything at once:**
   ```bash
   ./start-all.sh
   ```

2. **Check status:**
   ```bash
   ./dev-status.sh
   ```

3. **Stop everything:**
   ```bash
   ./stop-all.sh
   ```

## Individual Services

### Database Only
```bash
./start-database.sh    # Start PostgreSQL in Docker
```

### Backend Only
```bash
./start-backend.sh     # Start FastAPI server natively
```

### Frontend Only
```bash
./start-frontend.sh    # Start React dev server natively
```

## Service URLs

- **Frontend:** http://localhost:5173 (React/Vite)
- **Backend:** http://localhost:5151 (FastAPI)
- **API Docs:** http://localhost:5151/docs
- **Database:** localhost:5443 (PostgreSQL)

## Prerequisites

### Required Software
- **Docker Desktop** (for PostgreSQL database)
- **Python 3.8+** (for backend)
- **Node.js 18+** (for frontend)

### Environment Setup

1. **Environment variables** - Create `.env` file with:
   ```env
   # Database (points to Docker container)
   DB_HOST=localhost
   DB_PORT=5443
   DB_NAME=redditmon
   DB_USER=redditmon
   DB_PASSWORD=supersecret

   # Reddit API credentials
   REDDIT_CLIENT_ID=your_client_id
   REDDIT_CLIENT_SECRET=your_client_secret
   REDDIT_USERNAME=your_username
   REDDIT_PASSWORD=your_password
   REDDIT_USER_AGENT=reddit-claim-verifier/1.0

   # Brave Search API (optional)
   BRAVE_API_KEY=your_brave_api_key
   ```

2. **Brave API Key** (optional) - Create `BRAVEKEY` file with your API key

## Development Workflow

### Starting Up
```bash
# Option 1: Start everything
./start-all.sh

# Option 2: Start services individually
./start-database.sh
./start-backend.sh     # In separate terminal
./start-frontend.sh    # In separate terminal
```

### Monitoring
```bash
# Check status of all services
./dev-status.sh

# View logs (when using start-all.sh)
tail -f logs/backend.log
tail -f logs/frontend.log
```

### Shutting Down
```bash
# Stop everything
./stop-all.sh

# Or use Ctrl+C if running in foreground
```

## Script Details

| Script | Purpose | Description |
|--------|---------|-------------|
| `start-all.sh` | Complete setup | Starts database, backend, and frontend together |
| `start-database.sh` | Database only | Starts PostgreSQL container |
| `start-backend.sh` | Backend only | Starts FastAPI with virtual environment |
| `start-frontend.sh` | Frontend only | Starts React development server |
| `stop-all.sh` | Cleanup | Stops all services and containers |
| `dev-status.sh` | Monitoring | Shows status of all services |

## Troubleshooting

### Common Issues

1. **Docker not running**
   ```bash
   # Start Docker Desktop first, then:
   ./start-database.sh
   ```

2. **Database connection failed**
   ```bash
   # Check if database container is running:
   docker-compose ps db
   
   # Restart database:
   docker-compose restart db
   ```

3. **Backend won't start**
   ```bash
   # Check Python dependencies:
   cd backend
   source venv/bin/activate
   pip install -r requirements.txt
   ```

4. **Frontend won't start**
   ```bash
   # Check Node.js dependencies:
   cd frontend
   npm install
   ```

5. **Port conflicts**
   - Frontend (5173): Change in `frontend/vite.config.ts`
   - Backend (5151): Change in `backend/main.py` and scripts
   - Database (5443): Change in `docker-compose.yml` and `.env`

### Logs and Debugging

- **Backend logs:** `logs/backend.log` (when using `start-all.sh`)
- **Frontend logs:** `logs/frontend.log` (when using `start-all.sh`)
- **Database logs:** `docker-compose logs db`

### Reset Everything

```bash
# Stop all services
./stop-all.sh

# Remove containers and volumes
docker-compose down -v

# Clean logs
rm -rf logs/

# Restart fresh
./start-all.sh
```

## Development Notes

- Backend runs with auto-reload (`--reload` flag)
- Frontend runs with hot module replacement
- Database data persists in Docker volume
- Virtual environment is created automatically for backend
- All scripts include error checking and status messages