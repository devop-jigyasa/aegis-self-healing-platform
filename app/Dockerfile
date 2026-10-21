# syntax=docker/dockerfile:1
# --- Stage 1: Build Dependencies ---
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# --- Stage 2: Hardened Runtime Container ---
FROM python:3.11-slim AS runner

WORKDIR /app

# Security: Create non-root user and group
RUN groupadd -r aegisgroup && useradd -r -g aegisgroup -u 10001 aegisuser

# Copy installed wheels from builder
COPY --from=builder /root/.local /home/aegisuser/.local
ENV PATH=/home/aegisuser/.local/bin:$PATH

# Copy application source code
COPY main.py .
COPY static ./static

# Permissions
RUN chown -R aegisuser:aegisgroup /app /home/aegisuser

USER aegisuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
