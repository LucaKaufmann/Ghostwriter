# Ghostwriter Dockerfile
# Multi-stage build for minimal final image

# Stage 1: Frontend Builder
FROM node:22-alpine AS frontend-builder

WORKDIR /frontend

# Install dependencies
COPY frontend/package*.json ./
RUN npm ci --prefer-offline

# Copy source and build
COPY frontend/ ./
RUN npm run build


# Stage 2: Python Builder
FROM python:3.11-slim AS python-builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Stage 3: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 ghostwriter

# Copy virtual environment from builder
COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=ghostwriter:ghostwriter app/ ./app/
COPY --chown=ghostwriter:ghostwriter scripts/ ./scripts/
COPY --chown=ghostwriter:ghostwriter entrypoint.sh ./entrypoint.sh

# Copy frontend build output
COPY --from=frontend-builder --chown=ghostwriter:ghostwriter /frontend/build ./frontend/

# Create data directories and pre-compile Python bytecode for faster startup
RUN mkdir -p /app/data /app/output /app/logs && \
    chown -R ghostwriter:ghostwriter /app && \
    python -m compileall -q /opt/venv/lib/ app/ 2>/dev/null || true

# Switch to non-root user
USER ghostwriter

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    DATA_DIR=/app/data \
    OUTPUT_DIR=/app/output \
    LOGS_DIR=/app/logs

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run migrations then start the application
ENTRYPOINT ["./entrypoint.sh"]
