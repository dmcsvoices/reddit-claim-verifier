#!/bin/bash
# Start Reddit Monitor Backend for native development
# Requires PostgreSQL database to be running

echo "🐍 Starting Reddit Monitor Backend..."

# Check if we're in the right directory
if [ ! -f "backend/main.py" ]; then
    echo "❌ Error: backend/main.py not found. Run from project root."
    exit 1
fi

# Change to backend directory
cd backend

# Check if virtual environment exists, create if not
if [ ! -d "venv" ]; then
    echo "🔧 Creating Python virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Load environment variables from .env file
if [ -f "../.env" ]; then
    echo "🔧 Loading environment variables from .env..."
    export $(grep -v '^#' ../.env | xargs)
else
    echo "⚠️  Warning: .env file not found, using defaults"
    export DB_HOST="localhost"
    export DB_PORT="5443"
    export DB_NAME="redditmon"
    export DB_USER="redditmon" 
    export DB_PASSWORD="supersecret"
fi

# Load Brave API key if BRAVEKEY file exists
if [ -f "../BRAVEKEY" ]; then
    export BRAVE_API_KEY=$(cat ../BRAVEKEY | tr -d '\n')
    echo "✅ Brave API key loaded"
else
    echo "⚠️  Warning: BRAVEKEY file not found, web search may not work"
fi

# Load Together API key if TOGETHER file exists
if [ -f "../TOGETHER" ]; then
    export TOGETHER_API_KEY=$(cat ../TOGETHER | tr -d '\n')
    echo "✅ Together API key loaded"
else
    echo "⚠️  Warning: TOGETHER file not found, Together AI endpoints may not work"
fi

# Test database connection
echo "🗄️  Testing database connection..."
python3 -c "
import psycopg
import os
try:
    conn = psycopg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5443'),
        dbname=os.getenv('DB_NAME', 'redditmon'),
        user=os.getenv('DB_USER', 'redditmon'),
        password=os.getenv('DB_PASSWORD', 'supersecret')
    )
    conn.close()
    print('✅ Database connection successful')
except Exception as e:
    print(f'❌ Database connection failed: {e}')
    exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ Database not available. Start database first: ./start-database.sh"
    exit 1
fi

echo ""
echo "🚀 Starting FastAPI server on http://localhost:5151"
echo "   Press Ctrl+C to stop"
echo "   API docs: http://localhost:5151/docs"
echo ""

# Start the server
uvicorn main:app --host 0.0.0.0 --port 5151 --reload