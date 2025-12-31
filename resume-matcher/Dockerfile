
FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for pdfminer if needed
RUN apt-get update && apt-get install -y build-essential

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_sm

COPY . .

# Expose port 8000 (standard for FastAPI/Uvicorn)
EXPOSE 8000

# Command to run the app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
