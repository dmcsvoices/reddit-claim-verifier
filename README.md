# Reddit Claim Verifier

An automated fact-checking system for Reddit posts using a multi-stage LLM processing pipeline. The system monitors subreddits for new posts, identifies factual claims, researches them using web search, generates fact-based responses, and can post corrections back to Reddit.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.11+
- Node.js 18+ (for frontend)
- [Ollama](https://ollama.ai) for LLM serving
- Reddit API credentials
- Brave Search API key

### 1. Setup Environment

```bash
# Clone the repository
git clone <your-repo-url>
cd reddit-claim-verifier

# Copy environment template
cp .env.example .env

# Edit .env with your actual credentials
nano .env
```

### 2. Start Services

```bash
# Start database
docker-compose up -d db

# Start backend (will create tables automatically)
docker-compose up -d backend

# Start frontend
docker-compose up -d frontend
```

### 3. Setup LLM Endpoints

```bash
# Install Ollama models
ollama pull llama3.1:8b   # For triage and editorial
ollama pull llama3.1:70b  # For research and response

# Start Ollama servers (separate terminals)
OLLAMA_HOST=0.0.0.0:8001 ollama serve  # Fast endpoint
OLLAMA_HOST=0.0.0.0:8002 ollama serve  # Capable endpoint
```

### 4. Test the System

```bash
# Run test suite
python test_queue_system.py

# Access web interface
open http://localhost:5173

# Check API status  
curl http://localhost:5151/health
curl http://localhost:5151/queue/status
```

## 📋 Environment Configuration

Required environment variables in `.env`:

```env
# Database
DB_HOST=localhost
DB_PORT=5443
DB_PASSWORD=your_secure_password

# Reddit API (from https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret  
REDDIT_USERNAME=your_username
REDDIT_PASSWORD=your_password

# Brave Search API (from https://brave.com/search/api/)
BRAVE_API_KEY=your_brave_api_key

# LLM Endpoints
TRIAGE_ENDPOINT=http://localhost:8001
RESEARCH_ENDPOINT=http://localhost:8002
RESPONSE_ENDPOINT=http://localhost:8002
EDITORIAL_ENDPOINT=http://localhost:8001
```

## 🏗️ Architecture

### Processing Pipeline
```
Reddit Scan → Triage → Research → Response → Editorial → Post Queue
```

### Components
- **Backend**: FastAPI application with queue management
- **Frontend**: React + TypeScript dashboard
- **Database**: PostgreSQL with queue state management
- **LLM Agents**: Specialized agents for each processing stage
- **Tools**: Brave Search integration and database operations

## 📊 API Endpoints

### Core Operations
- `POST /scan` - Scan subreddit for new posts
- `GET /posts` - Retrieve recent posts  
- `GET /health` - System health check

### Queue Management
- `GET /queue/status` - Current processing status
- `GET /queue/stats` - Detailed queue statistics
- `POST /queue/retry/{post_id}` - Retry failed post
- `GET /posts/{post_id}/history` - Processing history

## 🧪 Testing

```bash
# Run full test suite
python test_queue_system.py

# Test individual components
cd backend
python -m pytest tests/

# Test with mock agents (no LLM required)
USE_MOCK_AGENTS=true python test_queue_system.py
```

## 🚀 Development

### Backend Development
```bash
cd backend
pip install -r requirements.txt
python main.py  # or uvicorn main:app --reload
```

### Frontend Development
```bash
cd frontend
npm install
npm run dev
```

### Adding New Agents
1. Create agent class in `backend/agents/`
2. Add tool definitions in `backend/tools/`
3. Update `backend/agents/agent_config.py`
4. Add to queue processing pipeline

## 📈 Monitoring

### Queue Status
- Web dashboard: http://localhost:5173
- API status: http://localhost:5151/queue/status
- Database queries for detailed analysis

### Performance Metrics
- Processing throughput per stage
- Success/failure rates  
- Average processing times
- Cost tracking per model

## 🔧 Configuration

### Queue Settings
Adjust processing intervals and concurrency in `backend/queue/queue_manager.py`:

```python
QUEUE_CONFIG = {
    "poll_intervals": {
        "triage": 5,      # Fast processing
        "research": 15,   # Slower due to web search
        "response": 10,   # Moderate complexity
        "editorial": 5    # Fast editing
    },
    "max_retries": 3,
    "assignment_timeout": 300
}
```

### Agent Configuration
Model and endpoint settings in `backend/agents/agent_config.py`:

```python
AGENT_CONFIG = {
    "triage": {
        "model": "llama3.1:8b",
        "max_concurrent": 4,
        "timeout": 30
    },
    # ... other agents
}
```

## 📚 Documentation

- [Project Overview](PROJECT_DOCUMENTATION.md)
- [Queue System Design](QUEUE_MANAGEMENT_DESIGN.md)  
- [LLM Agents Design](LLM_AGENTS_DESIGN.md)
- [Development Guide](CLAUDE.md)

## 🔐 Security

- All credentials must be in environment variables
- Never commit `.env` or `secret/` files
- Use separate credentials for development/production
- Monitor API usage and costs

## 📝 License

[Your License Choice]

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality  
5. Submit a pull request

## 💡 Support

- Check the [Issues](../../issues) for common problems
- Review documentation in the `/docs` folder
- Test with mock agents first before debugging LLM issues