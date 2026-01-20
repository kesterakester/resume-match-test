
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Redis
RUN apt-get update && apt-get install -y \
    build-essential \
    redis-server \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Upgrade pip and install dependencies
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt --timeout 100 && \
    python -m spacy download en_core_web_sm

COPY . .

# Make start script executable
RUN chmod +x start.sh

# Expose port 8000
EXPOSE 8000

# Command to run the app using the start script
CMD ["./start.sh"]
