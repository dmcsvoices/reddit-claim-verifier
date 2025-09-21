#!/bin/bash
# Restart the backend to pick up new environment variables

echo "🔄 Restarting Reddit Monitor Backend..."

# Find and kill the current backend process
BACKEND_PID=$(pgrep -f "uvicorn main:app")
if [ -n "$BACKEND_PID" ]; then
    echo "🛑 Stopping current backend (PID: $BACKEND_PID)..."
    kill $BACKEND_PID
    sleep 3
    
    # Force kill if still running
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "   Force stopping backend..."
        kill -9 $BACKEND_PID
    fi
    echo "   Backend stopped"
else
    echo "ℹ️  No backend process found"
fi

# Start new backend
echo "🚀 Starting backend with new configuration..."
./start-backend.sh &

echo "✅ Backend restart initiated"
echo "   Check status: ./dev-status.sh"
echo "   View logs: tail -f logs/backend.log (if using start-all.sh)"