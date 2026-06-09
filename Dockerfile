FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default ChromaDB persistence path (Railway volume mount)
ENV CHROMA_PERSIST_DIR=/data/chroma_db

WORKDIR /app

# Install system dependencies for sentence-transformers
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for ChromaDB
RUN mkdir -p /data/chroma_db

# Railway provides PORT env var
ENV PORT=8000
EXPOSE ${PORT}

# Start the FastAPI server
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT}
