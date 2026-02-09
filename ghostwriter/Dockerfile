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


# Stage 2.5: whisper.cpp Builder
FROM python:3.11-slim AS whisper-builder

ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    cmake \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 https://github.com/ggml-org/whisper.cpp /opt/whisper && \
    if [ "${TARGETARCH:-}" = "arm64" ] || [ "$(uname -m)" = "aarch64" ]; then \
        CMAKE_FLAGS="-DCMAKE_C_FLAGS=-march=armv8-a -DCMAKE_CXX_FLAGS=-march=armv8-a"; \
    else \
        CMAKE_FLAGS=""; \
    fi && \
    cmake -S /opt/whisper -B /opt/whisper/build ${CMAKE_FLAGS} && \
    cmake --build /opt/whisper/build -j && \
    strip -s /opt/whisper/build/bin/whisper-cli || true


# Stage 3: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 ghostwriter

# Copy virtual environment from builder
COPY --from=python-builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Media download for YouTube/podcast audio
RUN pip install --no-cache-dir yt-dlp

# Copy whisper.cpp binary + shared libs
COPY --from=whisper-builder /opt/whisper/build/bin/whisper-cli /usr/local/bin/whisper-cli
COPY --from=whisper-builder /opt/whisper/build/src/libwhisper.so* /usr/local/lib/
COPY --from=whisper-builder /opt/whisper/build/ggml/src/libggml*.so* /usr/local/lib/
RUN ldconfig

# Copy application code
COPY --chown=ghostwriter:ghostwriter app/ ./app/
COPY --chown=ghostwriter:ghostwriter scripts/ ./scripts/
COPY --chown=ghostwriter:ghostwriter alembic/ ./alembic/
COPY --chown=ghostwriter:ghostwriter alembic.ini ./alembic.ini
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
