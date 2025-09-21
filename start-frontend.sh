#!/bin/bash
# Start Reddit Monitor Frontend for native development

echo "⚛️  Starting Reddit Monitor Frontend..."

# Check if we're in the right directory
if [ ! -f "frontend/package.json" ]; then
    echo "❌ Error: frontend/package.json not found. Run from project root."
    exit 1
fi

# Change to frontend directory
cd frontend

# Check if node_modules exists, install if not
if [ ! -d "node_modules" ]; then
    echo "📦 Installing Node.js dependencies..."
    npm install
fi

echo ""
echo "🚀 Starting React development server on http://localhost:5173"
echo "   Press Ctrl+C to stop"
echo ""

# Start the development server
npm run dev