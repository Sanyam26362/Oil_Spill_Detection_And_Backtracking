# Dockerfile
# G2: Multi-stage build — builder installs compiled dependencies;
# final stage is lean and runs as a non-root user.

# ---- Builder ----
FROM python:3.11-slim AS builder

WORKDIR /build

# System libraries required to compile Python extensions.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Final ----
FROM python:3.11-slim

# Runtime-only system libraries (shared objects linked by extensions).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgeos-c1v5 \
    libproj25 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled packages from builder.
COPY --from=builder /install /usr/local

# Create a non-root user.
RUN useradd -m appuser
USER appuser
WORKDIR /app

COPY --chown=appuser:appuser . .

EXPOSE 8000

# G2: HEALTHCHECK so Docker orchestrators can detect unhealthy containers.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health/ready || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]