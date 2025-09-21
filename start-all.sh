#!/bin/bash
# Start complete Reddit Monitor development environment
# This starts database, backend, and frontend in parallel

echo "🚀 Starting Reddit Monitor Complete Development Environment..."

# Function to kill background processes on exit
cleanup() {
    echo ""
    echo "🛑 Stopping all services..."
    
    if [ ! -z "$BACKEND_PID" ] && kill -0 $BACKEND_PID 2>/dev/null; then
        echo "   Stopping backend..."
        kill $BACKEND_PID
    fi
    
    if [ ! -z "$FRONTEND_PID" ] && kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "   Stopping frontend..."
        kill $FRONTEND_PID
    fi
    
    # Kill any remaining processes
    pkill -f "uvicorn main:app" 2>/dev/null || true
    pkill -f "npm run dev" 2>/dev/null || true
    
    echo "✅ All services stopped"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start database
echo "1. Starting database..."
./start-database.sh
if [ $? -ne 0 ]; then
    echo "❌ Failed to start database"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Start backend in background
echo "2. Starting backend..."
nohup ./start-backend.sh > logs/backend.log 2>&1 &
BACKEND_PID=$!

# Wait for backend to start
echo "   Waiting for backend to be ready..."
sleep 5
until curl -s http://localhost:5151/health >/dev/null 2>&1; do
    echo "   Backend not ready yet, waiting..."
    sleep 2
done
echo "   ✅ Backend ready"

# Start frontend in background
echo "3. Starting frontend..."
nohup ./start-frontend.sh > logs/frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait for frontend to start
echo "   Waiting for frontend to be ready..."
sleep 5
until curl -s http://localhost:5173 >/dev/null 2>&1; do
    echo "   Frontend not ready yet, waiting..."
    sleep 2
done
echo "   ✅ Frontend ready"

echo ""
echo "🎉 All services started successfully!"
echo ""
echo "📊 Services:"
echo "   • Database:  localhost:5443 (PostgreSQL)"
echo "   • Backend:   http://localhost:5151 (FastAPI + Queue Management)"
echo "   • Frontend:  http://localhost:5173 (React/Vite)"
echo ""
echo "📝 Real-time logs:"
echo "   • Backend:   tail -f logs/backend.log"
echo "   • Frontend:  tail -f logs/frontend.log"
echo ""
echo "🔗 Quick Links:"
echo "   • App:       http://localhost:5173"
echo "   • API docs:  http://localhost:5151/docs"
echo "   • Health:    http://localhost:5151/health"
echo "   • Queue:     http://localhost:5151/queue/status"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Keep script running and show log outputs
tail -f logs/backend.log logs/frontend.log &
TAIL_PID=$!

# Wait for user interrupt
wait

# Cleanup will be called automatically by trap