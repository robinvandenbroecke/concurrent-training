#!/bin/bash
# Start script for Concurrent Training API

cd /root/clawd/projects/concurrent-training
source .venv/bin/activate

echo "Starting Concurrent Training API..."
echo "UI will be available at: http://localhost:8000/static/index.html"
echo "API docs at: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Remove old db for clean start
rm -f concurrent_training.db

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
