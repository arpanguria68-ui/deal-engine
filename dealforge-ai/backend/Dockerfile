# DealForge AI Backend Dockerfile — DealForge 2.0
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    fonts-liberation \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (Docker layer caching)
COPY requirements.txt .

# Install Python dependencies + aiosqlite for SQLite async support
RUN pip install --no-cache-dir -r requirements.txt aiosqlite

# Copy the full application
COPY app/ ./app/

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite+aiosqlite:///./dealforge.db
ENV DEBUG=true
ENV DEFAULT_LLM_PROVIDER=gemini
ENV PAGEINDEX_MODE=local

# Expose port
EXPOSE 8000

# Run the application (no --reload to avoid subprocess issues)
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
