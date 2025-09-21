#!/bin/bash
# Start PostgreSQL database for native development
# This script starts only the database container

echo "🐘 Starting PostgreSQL database..."

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Start only the database container
docker-compose up -d db

echo "⏳ Waiting for database to be ready..."
sleep 3

# Wait for database to accept connections
until docker-compose exec -T db pg_isready -U redditmon -d redditmon >/dev/null 2>&1; do
    echo "   Database not ready yet, waiting..."
    sleep 2
done

echo "✅ PostgreSQL database is ready!"
echo "   Connection: postgresql://redditmon:supersecret@localhost:5443/redditmon"