# Multi-stage Dockerfile for Financial Reports Extractor
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    # For OpenCV and image processing
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    # For Tesseract OCR
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-spa \
    # For headless browser
    wget \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt requirements-dev.txt ./

# === DEVELOPMENT STAGE ===
FROM base as development

# Install all dependencies including dev dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-dev.txt

# Create directories
RUN mkdir -p storage/documents storage/temp storage/logs

# Copy source code
COPY . .

# Expose port
EXPOSE 8000

# Default command for development
CMD ["uvicorn", "src.adapters.web.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# === PRODUCTION STAGE ===  
FROM base as production

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install only production dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/

# Create directories and set permissions
RUN mkdir -p storage/documents storage/temp storage/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production command
CMD ["uvicorn", "src.adapters.web.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# === TARGET SELECTION ===
FROM ${BUILD_ENV:-production} as final