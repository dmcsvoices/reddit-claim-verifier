#!/bin/bash
echo "=== Testing Docker Setup ==="
echo "Backend on port 5151:"
curl -s http://localhost:5151/health | jq . 2>/dev/null || echo "Failed to connect to backend"

echo
echo "Frontend on port 5173:"
curl -s -I http://localhost:5173 | head -1 || echo "Failed to connect to frontend"

echo
echo "=== Port Test ==="
echo "Checking if backend is on 5151 (should work):"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5151/health

echo "Checking if backend is on 8000 (should fail):"
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/health --connect-timeout 2