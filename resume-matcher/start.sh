#!/bin/bash
set -m

# Start Redis
# Explicitly bind to 127.0.0.1 since we only need local access within the container
redis-server --daemonize yes --bind 127.0.0.1

# Wait for redis to come up
sleep 2

# Start Celery Worker in background
# We don't use --detach so we can see logs if needed, but we background it with &
celery -A tasks worker --loglevel=info &

# Start API in foreground
uvicorn main:app --host 0.0.0.0 --port 8000
