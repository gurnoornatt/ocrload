# =============================================================================
# STAGE 1: Build Dependencies (Build Environment)
# =============================================================================
FROM python:3.12-slim as builder

# Build arguments for better caching
ARG POETRY_VERSION=1.8.2

# Set environment variables for Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_HOME="/opt/poetry" \
    VIRTUAL_ENV="/app/.venv"

# Install system dependencies needed for building
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==$POETRY_VERSION

# Set work directory
WORKDIR /app

# Copy Poetry configuration files
COPY pyproject.toml poetry.lock ./

# Create virtual environment and install dependencies
RUN python -m venv $VIRTUAL_ENV \
    && . $VIRTUAL_ENV/bin/activate \
    && poetry install --only=main --no-root \
    && rm -rf $POETRY_CACHE_DIR

# =============================================================================
# STAGE 2: Production Runtime (Final Image)
# =============================================================================
FROM python:3.12-slim as production

# Runtime environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV="/app/.venv" \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PORT=8000

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set work directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Copy application code
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser pyproject.toml ./

# Create necessary directories and set permissions
RUN mkdir -p /app/logs /app/tmp \
    && chown -R appuser:appuser /app \
    && chmod -R 755 /app

# Create a Python startup script to handle PORT environment variable
RUN echo 'import os\nimport uvicorn\n\nif __name__ == "__main__":\n    port = int(os.getenv("PORT", 8000))\n    uvicorn.run("app.main:app", host="0.0.0.0", port=port)' > /app/start.py \
    && chmod +x /app/start.py

# Switch to non-root user
USER appuser

# Expose port
EXPOSE $PORT

# Health check (updated path to use environment variable correctly)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run the application (use Python startup script for better signal handling)
CMD ["python", "/app/start.py"] 