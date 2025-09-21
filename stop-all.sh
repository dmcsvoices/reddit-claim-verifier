#!/bin/bash
# Stop all Reddit Monitor services

echo "🛑 Stopping Reddit Monitor Development Environment..."

# Kill backend processes
echo "   Stopping backend processes..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "     ✅ Backend stopped" || echo "     ℹ️  No backend running"

# Kill frontend processes  
echo "   Stopping frontend processes..."
pkill -f "npm run dev" 2>/dev/null && echo "     ✅ Frontend stopped" || echo "     ℹ️  No frontend running"

# Stop database container
echo "   Stopping database..."
if docker-compose ps db --quiet 2>/dev/null | grep -q .; then
    docker-compose stop db
    echo "     ✅ Database stopped"
else
    echo "     ℹ️  No database container running"
fi

# Clean up log files if they exist
if [ -d "logs" ]; then
    rm -f logs/*.log
    echo "   Cleaned up log files"
fi

echo ""
echo "✅ All services stopped!"
echo ""
echo "💡 To restart: ./start-all.sh"