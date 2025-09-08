# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Architecture

This is a Reddit monitoring application with a full-stack architecture:

**Backend (FastAPI/Python)**
- Located in `backend/` directory
- FastAPI application in `main.py:9`
- Uses PRAW (Python Reddit API Wrapper) for Reddit API integration
- PostgreSQL database with psycopg for data persistence
- Posts table schema defined in `main.py:48-60`
- Reddit client configuration in `main.py:25-32`

**Frontend (React/TypeScript)**
- Located in `frontend/` directory  
- Vite-powered React application with TypeScript
- Main application logic in `frontend/src/App.tsx`
- API communication with backend at `http://localhost:5151`

**Database**
- PostgreSQL 16 running in Docker container
- Default connection: host=db, port=5432, db=redditmon, user=redditmon
- Posts table stores Reddit submissions with metadata

## Development Commands

**Docker Development (Recommended)**
```bash
# Start all services (database, backend, frontend)
docker-compose up

# Start in background
docker-compose up -d

# Stop all services
docker-compose down
```

**Frontend Development**
```bash
cd frontend
npm run dev      # Start development server (port 5173)
npm run build    # Build for production
npm run preview  # Preview production build
```

**Backend Development**
```bash
cd backend
# Install dependencies
pip install -r requirements.txt

# Run development server directly
python main.py   # Starts on port 5151
# OR
uvicorn main:app --host 0.0.0.0 --port 5151
```

**Testing**
```bash
# Run connection tests
./test.sh
```

## Service Ports

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:5151` 
- Database: `localhost:5443` (mapped from container port 5432)

## API Endpoints

- `GET /health` - Health check with database status
- `GET /posts` - Retrieve recent posts (limit 10)
- `POST /scan` - Scan subreddit for new posts
- `POST /dummy-insert` - Insert test post

## Key Configuration

**Reddit API Credentials**
- Configured via environment variables: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD, REDDIT_USER_AGENT
- Get credentials from https://www.reddit.com/prefs/apps
- Set in `.env` file, never commit credentials

**Database Connection**  
- Environment variables: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
- Docker Compose uses environment variable substitution
- Default development values provided with overrides

**CORS Configuration**
- Backend allows all origins (`allow_origins=["*"]`) in `main.py:13`

## Database Schema

Posts table (`main.py:49-58`):
- `id` - Serial primary key
- `reddit_id` - Unique Reddit post ID
- `title`, `author`, `url`, `body` - Post content
- `created_utc` - Post creation timestamp
- `inserted_at` - Database insertion timestamp