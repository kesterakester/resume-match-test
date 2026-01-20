#!/bin/bash

# Start Redis in the background (using internal system service or custom script depending on container)
# Since we are in a single container environment often on PaaS or simple runners, we might need to rely on 
# a managed Redis or install and run it locally if this container is the 'world'.
# However, user mentioned AWS EC2 with auto-deployment. 
# We'll assume the container needs to run everything or connect to external infra.
# Given the user wants to "commit -> redeploy docker", this likely builds ONE image.

# Start Redis Server
redis-server --daemonize yes

# Start Celery Worker in the background
celery -A tasks worker --loglevel=info --detach

# Start FastAPI App
uvicorn main:app --host 0.0.0.0 --port 8000
