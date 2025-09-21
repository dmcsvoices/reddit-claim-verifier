# Development Scripts Guide

This document explains how to use the development scripts for running Reddit Monitor components independently.

## 🚀 Quick Start Scripts

### Independent Component Startup

Run these scripts in **separate terminal windows** to see real-time logs:

```bash
# Terminal 1: Start Database
./start-database.sh

# Terminal 2: Start Backend (with real-time logs)
./start-backend.sh

# Terminal 3: Start Frontend
./start-frontend.sh
```

### All-in-One Startup

```bash
# Start everything together (logs go to files)
./start-all.sh
```

## 📋 Script Reference

### Core Scripts

| Script | Purpose | Output |
|--------|---------|---------|
| `./start-database.sh` | Start PostgreSQL container | Terminal |
| `./start-backend.sh` | Start FastAPI backend with queue workers | **Real-time terminal logs** |
| `./start-frontend.sh` | Start React development server | Terminal |
| `./start-all.sh` | Start all services in background | Logs to `logs/` directory |

### Management Scripts

| Script | Purpose |
|--------|---------|
| `./stop-all.sh` | Stop all services and clean up |
| `./restart-backend.sh` | Restart just the backend |
| `./dev-status.sh` | Check status of all services |

## 🔍 Real-Time Backend Monitoring

### To See Live Backend Activity:

**Option 1: Independent Backend (Recommended for debugging)**
```bash
# Stop current backend first
./stop-all.sh

# Start components separately
./start-database.sh           # Terminal 1
./start-backend.sh           # Terminal 2 - REAL-TIME LOGS HERE
./start-frontend.sh          # Terminal 3
```

**Option 2: Monitor Background Logs**
```bash
# If using start-all.sh, monitor logs with:
tail -f logs/backend.log
```

### What You'll See in Real-Time Backend Logs:

```
🚀 Starting triage stage worker
🚀 Starting research stage worker
🚀 Starting response stage worker
🚀 Starting editorial stage worker
✅ Processing post 123 in triage queue
📊 Triage agent analyzing post: "New study shows..."
✅ Triage completed for post 123, moving to research
🔍 Research agent investigating claims...
✅ Research completed for post 123, moving to response
💬 Response agent generating reply...
✅ Response completed for post 123, moving to editorial
📝 Editorial agent polishing response...
✅ Editorial completed for post 123, ready for posting
```

## ⚙️ Environment Setup

### Required Files:

1. **BRAVEKEY** - Contains Brave Search API key
   ```bash
   echo "your_brave_api_key_here" > BRAVEKEY
   ```

2. **.env** - Environment variables (optional, has defaults)
   ```
   DB_HOST=localhost
   DB_PORT=5443
   DB_NAME=redditmon
   DB_USER=redditmon
   DB_PASSWORD=supersecret
   ```

### Dependencies:

- **Docker** - For PostgreSQL database
- **Python 3.8+** - For backend
- **Node.js 16+** - For frontend

## 🔄 Common Workflows

### Development with Real-Time Monitoring:
```bash
# 1. Start database
./start-database.sh

# 2. Start backend in separate terminal (see real-time activity)
./start-backend.sh

# 3. Start frontend in separate terminal
./start-frontend.sh

# 4. Check status anytime
./dev-status.sh
```

### Quick Testing:
```bash
# Start everything quickly
./start-all.sh

# Check status
./dev-status.sh

# Monitor backend activity
tail -f logs/backend.log
```

### Clean Restart:
```bash
# Stop everything
./stop-all.sh

# Start fresh
./start-all.sh
```

## 📊 Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | http://localhost:5173 | Main application UI |
| Backend API | http://localhost:5151 | API server |
| API Docs | http://localhost:5151/docs | Swagger documentation |
| Health Check | http://localhost:5151/health | Service health status |
| Queue Status | http://localhost:5151/queue/status | Queue management status |
| Database | localhost:5443 | PostgreSQL (docker) |

## 🛠️ Troubleshooting

### Backend Not Starting:
```bash
# Check database is running
./dev-status.sh

# Check BRAVEKEY file exists
ls -la BRAVEKEY

# Check for port conflicts
lsof -i :5151
```

### Frontend Not Starting:
```bash
# Check if dependencies installed
cd frontend && npm install

# Check for port conflicts
lsof -i :5173
```

### Database Issues:
```bash
# Restart database
docker-compose restart db

# Check database logs
docker-compose logs db
```

## 💡 Tips

1. **Use independent scripts during development** to see real-time backend activity
2. **Use start-all.sh for quick testing** when you don't need to monitor logs
3. **Check dev-status.sh regularly** to verify all services are healthy
4. **Monitor logs/backend.log** if using start-all.sh and need to debug issues
5. **Use restart-backend.sh** to quickly restart just the backend after changes